# IAM
This repository is for managing authorization that resembles IAM in AWS.<br><br>
Specific requirements are as follows:
- A user may or may not have (a) group(s).
- A user can make a purchase to get a certain permission
- A group can make a group-level purchase by which the maximum amount of access permission given to the group is defined.
- A group can make customizable roles
    - The role can be assigned to a user when user is added to the group
    - As a user can potentially belong to multiple groups, the access permission should be appropriately granted/revoked


## Set up 
```
poetry install
```

## Update
```
poetry self update
```


## Formatting
```
make check
```


## Architecutre pattern explained
### Aggregate
Aggregate is transaction boundary, consisting of aggregate root, sub entities and value objects.
It is the smallest unit that can be 'atomically' treated, meaning that if you have to deal with
multiple aggregates, the operation(transaction) must be separated using, preferrably, eventual consistency.<br>


#### State changes of Aggregate
Aggregate's state must be versioned so it can provide optimistic locking feature thereby alleviating performance
degradation while keeping operations in atomic transaction.
Any state change is considered an 'event' that belongs to a specific aggregate. For example:<br>
```python
#app.utils.models.aggregate_root

@dataclass
class Aggregate:
    class Event(domain_event.DomainEvent):
        def mutate(self, obj: Aggregate | None) -> "Aggregate":
            """
            Changes the state of the aggregate
            according to domain event attriutes.
            """
            # Check sequence
            if not isinstance(obj, Aggregate):
                raise Aggregate.NotAggregateError
            next_version = obj.version + 1
            if self.version != next_version:
                raise obj.VersionError(self.version, next_version)
            # Update aggregate version
            obj.version = next_version

            obj.update_dt = self.timestamp
            # Project obj
            self.apply(obj)
            return obj

        def apply(self, obj) -> None:
            pass
```

The Aggregate provides API for event with two methods:<br>
- `mutate()`
- `apply()`

The `mutate()` firstly checks if the given object is an aggregate instance and then adds version count by 1.
if its own version is not equal to the subsequent version, it errors out. Otherwise, it stored the version
as aggregate's version, updating timestamp and apply `apply()` function.<br><br>

`apply()` function is passed down to concrete class and it should be an implementation of set of rules optionally
applicable when the event is triggered. You can consider this as an event hook.<br><br>

#### Triggering event
An event is triggered and applied to aggregate by `_trigger_()` function as follows.<br>
```python
#app.utils.models.aggregate_root
@dataclass
class Aggregate:
    ...
    def _trigger_(
        self,
        event_class: Type["Aggregate.Event"],
        **kwargs,
    ) -> None:
        next_version = self.version + 1
        try:
            event = event_class(  # type: ignore
                id=self.id,
                version=next_version,
                timestamp=datetime.now(),
                **kwargs,
            )
        except AttributeError:
            raise
        # Mutate aggregate with domain event
        event.mutate(self)

        # Append the domain event to pending events
        self.events.append(event)

    def _collect_(self) -> Iterator[Event]:
        """
        Collect pending events
        """
        while self.events:
            yield self.events.popleft()

``` 
As you can see, the `_trigger_()` function takes concrete event that inherits `Aggregate.Event` and keyword arguments.
After creating the event, it mutates `self` which is the aggregate with event's `mutate()` method, consequently applying
`apply()` method to the aggregate. After the `mutate()` method is invoked, the aggregate appends event to its events collection
So the events can be either populated to eventstore or outbox depending on implementation detail through `_collect_()` method .<br><br>


#### Creating an aggregate instance
Here comes an example of how `Aggregate.Event` can be used:<br>

```python
#app.utils.models.aggregate_root
@dataclass
class Aggregate:
    class Created(Event):
        """
        Domain event for creation of aggregate
        """
        topic: str

        def mutate(self, obj: "Aggregate" | None) -> "Aggregate":
            # Copy the event attributes
            kwargs = self.__dict__.copy()
            id = kwargs.pop("id")
            version = kwargs.pop("version")
            create_dt = kwargs.pop("timestamp")

            # To distinguish event that goes out to different service
            kwargs.pop("externally_notifiable",None) 
            # To distinguish event that affects other aggregate within the bounded context
            kwargs.pop("internally_notifiable",None) 

            # Get the root class from topicm, using helper function
            aggregate_class = resolver.resolve_topic(kwargs.pop("topic"))

            return aggregate_class(
                id=id, version=version, create_dt=create_dt, **kwargs
            )

    @classmethod
    def _create_(
        cls,
        event_class: Type["Aggregate.Created"],
        **kwargs,
    ):
        event = event_class(  # type: ignore
            id=kwargs.pop("id", uuid4()),
            version=1,
            topic=resolver.get_topic(cls),
            timestamp=datetime.now(),
            **kwargs,
        )

        # Call Aggregate.Created.mutate
        aggregate = event.mutate(None)
        aggregate.events.append(event)
        return aggregate
```
One might be curious why `Created` which inherits `Aggregate.Event` needs its own implemenation for `mutate()` method.
That's because in DDD, any state change is made through an event but then when created, there is no aggregate to be changed.
That means the event object, which is, in this context, `Aggregate.Created` cannot take Aggregate object as its argument.
Therefore, what `mutate()` method actually does is providing the same interface as other events while stuffing the attributes
for the given aggregate. Later on, the importance of this implementation becomes particularly apparent when rehydrating an aggregate<br><br>

Then, when `_create_()` is called for? You may have notived that I haven't mentioned when `_trigger_()` is invoked as well.
Calls for both `_create_()` and `_trigger_()` are implemented within `command method`, concrete methods that are specific to concrete aggregate.
For example:<br>
```python
#app.domain.iam
class User(aggregate_root.Aggregate):
    @classmethod
    def create(cls, msg: commands.CreateUser):
        """
        Create User
        """
        # TODO password hashing logic

        return super()._create_(cls.Created, name=msg.name, email=msg.email)

```
Here, you can see that `User` is an aggregate that inherit `Aggregate` abstract class and its `create()` method calls for its super class's `_create_()`.<br><br>



### Mapper
When event-sourced model is chosen as source of truth for entire system by which a lot of different read models could be made,
we have to think about how we can store different types of events in a common format. `Mapper` is what enables storing them in a organized way.
A mapper consists of three potential components:<br>
- `transcoder`
- `cipher`
- `compressor`

As you can guess through their name, the role of each component is self-evident. There is no clear naming convention for the method and its signature, but
they will look like the following:<br>

```python
#app.utils.events.mapper
@dataclass
class Mapper(Generic[TDomainEvent], metaclass=SignletonMeta):
    transcoder: AbstractTranscoder = field(init=False)
    cipher: Cipher | None = None
    compressor: Compressor | None = None

    def __post_init__(self):
        if not hasattr(self, "transcoder"):
            self.transcoder = transcoder

    def _convert_domain_event(
        self, domain_event: TDomainEvent
    ) -> tuple[UUID, int, str, bytes]:
        """
        Parses a domain event object returning id, version, topic, state
        """
        topic: str = resolver.get_topic(domain_event.__class__)
        d: dict = copy(domain_event.__dict__)
        _id = d.pop("id")
        _id = str(_id) if isinstance(_id, UUID) else _id
        _version = d.pop("version")

        state: bytes = self.transcoder.encode(d)

        if self.compressor:
            state = self.compressor.compress(state)
        if self.cipher:
            state = self.cipher.encrypt(state)
        return _id, _version, topic, state
    ...

```
Firstly, `_convert_domain_event()` takes domain event raised from an aggregate, and takes the following from the domain event:
- aggregate_id
- version of the given aggregate
- state of an aggregate 

Note how all the state of aggregate is encoded into bytes using transcoder. 

#### Transcoder & Transcoding
Transcoder should take a role of encoding and decoding state of an aggregate so you publish or store the event to any other external components.
So, the abstract transcoder class has essentially two methods:
```python
#app.utils.events.mapper
class AbstractTranscoder(ABC):
    """
    Abstract base class for transcoders
    """

    @abstractmethod
    def encode(self, o: Any) -> bytes:
        pass

    @abstractmethod
    def decode(self, d: bytes) -> Any:
        pass
```
How the encode and decode is done is implementation detail. In this project, I used `JSONEncoder` and `JSONDecoder` from standard library. 

```python
#app.utils.events.mapper
@dataclass
class Transcoder(Generic[TTranscoding], AbstractTranscoder):
    types: dict[type, Transcoding] = field(default_factory=dict)
    names: dict[str, Transcoding] = field(default_factory=dict)
    encoder: json.JSONEncoder = field(init=False)
    decoder: json.JSONDecoder = field(init=False)

    def __post_init__(self):
        self.encoder = json.JSONEncoder(default=self._encode_dict)
        self.decoder = json.JSONDecoder(object_hook=self._decode_dict)

    def _encode_dict(self, o: Any) -> dict[str, str | dict]:
        try:
            transcoding: Transcoding = self.types[type(o)]
        except KeyError:
            raise TypeError(
                f"Object of type {o.__class__.__name__} is not serializable!"
            )
        else:
            return {
                "__type__": transcoding.name,
                "__data__": transcoding.encode(o),
            }

    def _decode_dict(self, d: dict[str, str | dict]) -> Any:
        if set(d.keys()) == {"__type__", "__data__"}:
            t = d["__type__"]
            t = cast(str, t)
            transcoding = self.names[t]
            return transcoding.decode(d["__data__"])
        else:
            return d

    def encode(self, o: Any) -> bytes:
        return self.encoder.encode(o).encode("utf8")

    def decode(self, d: bytes) -> Any:
        return self.decoder.decode(d.decode("utf8"))

```
So, encoder is initialized in `__post_init__` method using `_encode_dict` method which takes any type and looks up the key with `self.types`, which means
there must be encoderable and decorable transcoding registration process; that will be convered soon. Getting back to `_encode_dict`, it returns dictionary of
`__type__` key with the value of the name of transcoding, and `__data__` with the value of encoded data. As a side note, `json.JSONEncoder` has its own method 
called `encode(o)` which takes any object. When it does NOT know how to encode the type, `default` method of `json.JSONEncoder` is called, going through the custom, 
`_encode_dict` method. The big picture is therefore, when the public interface `encode` method is invoked, it uses `json.JSONEncoder` by default and when it can't find the way
to encode the given object, it then relies on `_encode_dict`. Finally, all encoded dictionary is convereted to `utf8` by `.encode('utf8')` attached at the end.<br><br>

Now, let's look at how we register transcoding for inencoderable types:
```python
#app.utils.events.mapper
class Transcoding(ABC):
    type: type
    name: str

    @staticmethod
    @abstractmethod
    def encode(o: Any) -> str | dict:
        pass

    @staticmethod
    @abstractmethod
    def decode(d: str | dict) -> Any:
        pass


@dataclass
class Transcoder(Generic[TTranscoding], AbstractTranscoder):
    ...

    #decorator for registeration of transcodings
    def register(self, transcoding: TTranscoding):
        self.types[transcoding.type] = transcoding
        self.names[transcoding.name] = transcoding
    ...
```

Note that `register` method is added to register Transcoding in ad-hoc manner. Let's see how we can define transcoding for unserializable type. 
```python
#app.utils.events.mapper
transcoder: Transcoder = Transcoder()

@transcoder.register
class UUIDAsHex(Transcoding):
    type = UUID
    name = "uuid_hex"

    @staticmethod
    def encode(o: UUID) -> str:
        return o.hex

    @staticmethod
    def decode(d: str | dict) -> UUID:
        assert isinstance(d, str)
        return UUID(d)

```
Here, we override `encode` and `decode` to allow for encoding and decoding. You can apply similar approach to other types such as timestamp and decimal.<br><br>


#### Converting domain event to stored event or another
Now that we've gone through all the transcoding details, let's see how we can convert domain event to another using mapper.
```python
from .domain_event import DomainEvent, StoredEvent, OutBoxEvent

#app.utils.events.mapper
TDomainEvent = TypeVar("TDomainEvent", bound=DomainEvent)

@dataclass
class Mapper(Generic[TDomainEvent], metaclass=SignletonMeta):
    ...

    def from_domain_event_to_stored_event(self, domain_event: TDomainEvent) -> StoredEvent:
        _id, _version, topic, state = self._convert_domain_event(domain_event)

        return StoredEvent(  # type: ignore
            id=_id,
            version=_version,
            topic=topic,
            state=state,
        )

    def from_domain_event_to_outbox(self, domain_event: TDomainEvent) -> OutBoxEvent:
        _id, _, topic, state = self._convert_domain_event(domain_event)

        return OutBoxEvent(  # type: ignore
            aggregate_id=_id,
            topic=topic,
            state=state,
        )

    def from_stored_event_to_domain_event(self, stored: StoredEvent) -> TDomainEvent:
        dictified_state = self._convert_stored_event(stored)
        cls = resolver.resolve_topic(stored.topic)
        assert issubclass(cls, DomainEvent)
        domain_event: TDomainEvent = object.__new__(cls)
        return domain_event.from_kwargs(**dictified_state)
    ...
```
You can see that domain event is convereted firstly using `_convert_domain_event` method that applies
comporession and encyprtion method if implemented together with encoding method to the event and render
`StoredEvent` from `from_domain_event_to_stored_event` and `OutBoxEvent` from `from_domain_event_to_outbox`. 
Outbox pattern is beyond the scope of this discussion but briefly it is a pattern to ensure event is not missing
by storing an event in the same atomic transaction with domain event.<br><br>

Conversely, you can also convert `StoredEvent` to `DomainEvent` using `from_stored_event_to_doamin_event` with the decoding strategy explained.


### Port-Adapter Pattern
This project assumes port-adapter pattern, also known as hexagonal architecture so you can follow dependency inversion principle whereby you have
NO dependency nor knowledge of the underlying infrastructure. So you can see that all the infra-related stuff including ORM mapping, eventstore, repository is 
housed under adapters.<br>
```
app
│   __init__.py
│   config.py
└───adapters
│   │   __init__.py
│   │   eventstore.py
│   │   orm.py
│   │   repository.py
...
```
Here, you may be asking then without presentation layer, how can you receive client requests and respond to it? Well, the true benefit of having DIP here is that
the entire application is not tied to a specific framework or solution - FastAPI, Redis, Kafka for example. It means that if you are to publish and comsume data to and from Kafka, for instance, 
you can have its own dedicated entrypoints and also have FastAPI entrypoint separately, which would look like:<br>
```
app
│   __init__.py
│   config.py
└───adapters
│   │   __init__.py
│   │   eventstore.py
│   │   orm.py
│   │   repository.py
└───entrypoints
│   │ kafka_entry.py
│   │ fast_app.py
...
```
What it indicates is that your application handles commands coming in from multiple different input sources with one version control system. And as you can imagine, the roles of entrypoint are
basically making input understandable to your service by parsing, validating the data and putting the data into commands which were defined in domain layer and invoke an appropriate handler defined in servie layer.
So the file architecture again would look like this:<br>

```
app
│   __init__.py
│   config.py
└───adapters
│   │   __init__.py
│   │   eventstore.py
│   │   orm.py
│   │   repository.py
└───entrypoint
│   │ __init__.py
│   │ kafka_entry.py
│   │ fast_app.py
└───domain
│   │ __init__.py
│   │ commands.py
└───service_layer
│   │ handlers.py
...
```

