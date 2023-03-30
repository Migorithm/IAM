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
`StoredEvent` from `from_domain_event_to_stored_event`.<br><br>

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

### Repository
Repository is a simplifying abstraction over data storage that enables decoupling core logics from infrastructural concerns. Plus, repository is the public interface through which we can access aggregate, thereby enforcing the rule that says 'aggregates are the only way into our domain model.' You do not want to break that rule because otherwise you may fiddle with subentity of an aggregate, messing up the versioning, sabotaging sound transaction boundary.<br>

```python
#app.adapters.repository
class AbstractRepository(ABC):
    def add(self, *obj, **kwargs):
        self._add_hook(*obj, **kwargs)
        return self._add(*obj, **kwargs)

    def _add_hook(self, *obj, **kwargs):
        pass

    def add(self, *obj, **kwargs):
        self._add_hook(*obj, **kwargs)
        return self._add(*obj, **kwargs)

    def _add_hook(self, *obj, **kwargs):
        pass


    async def get(self, ref: str | UUID, **kwargs):
        res = await self._get(ref)
        self._get_hook(res)
        return res

    def _get_hook(self, aggregate):
        pass

    async def list(self):
        res = await self._list()
        return res

    @abstractmethod
    def _add(self, *obj, **kwargs):
        raise NotImplementedError

    # @abstractmethod
    async def _list(self):
        raise NotImplementedError

    @abstractmethod
    async def _get(self, ref):
        raise NotImplementedError

    class OperationalError(Exception):
        pass

    class IntegrityError(Exception):
        pass

    class AggregateNotFoundError(Exception):
        pass
```
This `AbstractRepository` exposes public API. Note that `add` method not only returns the result of `_add` which subclass must override but also adds `_add_hook` just in case there is some additional operation required, namely template method pattern.<br><br>

In this project, the followings are implemented:
- `SqlAlchemyRepository` : Repository for SQLAlchemy which is itself abstraction over RDBMS data storage.
- `OutboxRepository` : This inherits SqlAlchemyRepository just as it happens that RDBMS is source of truth. However, this can be changed if source of truth is not anymore RDBMS. 
- `EventRepository` : This is yet another Repository which inherit AbstractSqlAlchemyRepository, meaning that its implementation detail and how it overrides methods are different as query pattern diverges. 
<br>

One more element that's part of repository is `EventRepositoryProxy` which is basically a proxy to `EventRepository`. What is does is basically wraps the `EventRepository` and adds more bahaviour before and after the access to events stored in eventstore. All the repositories are initialized in UnitOfWork, the concept of which will be explained later.  

#### SqlAlchemyRepository
```python
#app.adapters.repository
class SqlAlchemyRepository(Generic[TAggregate], AbstractSqlAlchemyRepository):
    def __init__(self, model: TAggregate, session: AsyncSession):
        self.model = model
        self.session = session
        self._base_query = select(self.model)
        self.external_backlogs: deque[aggregate_root.Aggregate.Event] = deque()
        self.internal_backlogs: deque[aggregate_root.Aggregate.Event] = deque()
        
```
Simply put, `SqlAlchemyRepository` is for `domain model` which is, complexity-wise, notch below `event-sourced model`. That's the reason why it takes `model:TAggregate` so it can be used for read model as well as write model.<br>

#### OutboxRepository
```python
#app.adapters.repository
class OutboxRepository(SqlAlchemyRepository):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mapper: Mapper[aggregate_root.Aggregate.Event] = Mapper()

    def _add(self, *obj: aggregate_root.Aggregate.Event):
        """
        Map the obj to Outbox
        """
        for domain_event in obj:
            _id, _, topic, state = self.mapper._convert_domain_event(domain_event)
            self.session.add(
                OutBox(id=uuid4(), aggregate_id=_id, topic=topic, state=state)
            )

```
Extending `SqlAlchemyRepository`, it overrides `_add` method to convert domain model to storable form using `Mapper`. Its `_get` method is not to be used so exception raising code was implemented.<br>

#### EventRepository
```python
#app.adapters.repository
class EventRepository(AbstractSqlAlchemyRepository):  
    ...

    async def _add(self, stored_events: Sequence[StoredEvent], **kwargs) -> None:
        await self._insert_events(stored_events)

    async def _insert_events(
        self,
        events: Sequence[StoredEvent],
        *,
        tb_name: str | None = None,
        **kwargs,
    ) -> None:
        if len(events) == 0:
            return

        tb_name = self._events_table if tb_name is None else tb_name
        keys = tuple(events[0].__dict__.keys())

        raw_query = text(
            f"""
            INSERT INTO {tb_name} ({",".join(keys)})
            VALUES ({",".join((":"+k for k in keys))})
        """
        )
        try:
            await self.session.execute(
                raw_query,
                [e.__dict__ for e in events],
            )
        except Exception as e:
            raise self.IntegrityError(e)

    async def _get(
        self,
        aggregate_id: UUID,
        # gt: int | None = None,
        # lte: int | None = None,
        # desc: bool | None = False,
        # limit: int | None = None
    ) -> list[StoredEvent]:
        # TODO need to add conditions
        raw_query = text(
            f"""
            SELECT * FROM {self._events_table}
            WHERE id = :id
        """
        )
        c: CursorResult = await self.session.execute(raw_query, dict(id=aggregate_id))

        stored_events = [
            StoredEvent.from_kwargs(**row._mapping) for row in c.fetchall()
        ]

        return stored_events

```
Regarding complexity, `event-sourced model` is the most complicated, so much that you don't event want to think of getting multiple aggregates without CQRS. In fact, implementing CQRS becomes imperative when introducing the event-sourced model for a number of reasons, topic that's beyond the scope of this section.<br>

To support bulk insert, SQLAlchemy core syntax was used in `_insert_events`. Note that `_get` method takes every events given the aggregate id and return stored events to its caller, which is in this context `EventRepositoryProxy`

#### EventRepositoryProxy
```python
#app.adapters.repository
class EventRepositoryProxy(AbstractSqlAlchemyRepository):
    def __init__(self, *, session: AsyncSession):
        self.mapper: Mapper[aggregate_root.Aggregate.Event] = Mapper()
        self.repository: EventRepository = EventRepository(
            session=session, event_table_name=event_store.name
        )
        self.external_backlogs: deque[aggregate_root.Aggregate.Event] = deque()
        self.internal_backlogs: deque[aggregate_root.Aggregate.Event] = deque()

    def _add_hook(self, *obj: TAggregate):
        for o in obj:
            self.external_backlogs.extend(
                filter(lambda e: e.externally_notifiable, o.events)
            )
            self.internal_backlogs.extend(
                filter(lambda e: e.internally_notifiable, o.events)
            )

    async def _add(self, *aggregate: TAggregate, **kwargs) -> None:
        pending_events = []
        for agg in aggregate:
            pending_events += list(agg._collect_())

        # To Aggregate
        await self.repository.add(
            tuple(map(self.mapper.from_domain_event_to_stored_event, pending_events)),
            **kwargs,
        )

    async def _get(
        self,
        aggregate_id: UUID,
    ) -> aggregate_root.Aggregate:
        aggregate = None

        for domain_event in map(
            self.mapper.from_stored_event_to_domain_event,
            await self.repository.get(aggregate_id),
        ):
            aggregate = domain_event.mutate(aggregate)
        if aggregate is None:
            raise self.AggregateNotFoundError
        assert isinstance(aggregate, aggregate_root.Aggregate)
        return aggregate
```
Wrapper around `EventRepository` that adds more features such as `_add_hook` for distingguishing trasmittable events that go either to different aggregate or to different services, namely external backlogs and internal backlogs. Plus, as it takes `Mapper` as its attribute, it also handles directly mapping before and after accessing underlying `EventRepository`. Most notably, `_get` rehydrates aggregate with the events taken from `EventRepository` and return the aggregate. 


### ORM
To achieve DIP, your domain model should depend on ORM but rather, ORM should depend on your domain model. This becomes particularly important when you have to port database storage to NoSQL-based one from RDBMS. Using `declarative mapping`, however, hinders you from doing so as it is used with domain model where it is declared. For that reason in this project, `classical mapping` and then the table object is mapped to domain model using `start_mappers()` method.<br>

```python
#app.adapters.orm

...

def start_mappers():
    mapper_registry.map_imperatively(
        iam.User,
        users,
        properties={
            "group_roles": relationship(
                iam.GroupRoles,
                back_populates="users",
                secondary=group_role_user_associations,
                primaryjoin=f"{users.name}.c.id=={group_role_user_associations.name}.c.user_id",
                secondaryjoin=f"{group_role_user_associations.name}.c.group_role_id=={group_roles.name}.c.id",
                uselist=True,
                collection_class=set,
                innerjoin=False,
            ),
        },
        eager_defaults=True,
    )
    ...
```
Mapping method deserves some explanation. `map_imperatively` is method that's attached to `sqlalchemy.orm.registry` which is initialized with `sqlalchemy.MetaData`. What it essentially does is to map table object to domain model(or class) you define in your project. Here, `iam.User` and `iam.GroupRoles` are defined in `app.domain.iam`.<br><br>

With the two positional argument being domain model and table model passed, there are some keyword arguments worth paying attention to:<br>
- `properties`
- `eager_defaults`
- `version_id_col`
- `version_id_generator`

#### `properties`
This keyword argument passed to `map_imperatively` is mainly to define relationship, hence requiring `sqlalchemy.relationship`.<br><br> 

Short note on keyword argument passed to `relationship` function:<br>
- `back_populates` : how the given referent calls referer. That is to say, how `iam.GroupRoles` referes to `iam.User`. 
- `secondary` : this is an example of how you achieve `many to many` relationship in SQLAlchemy. Here association table is `group_role_user_association` and it must have foreign keys pointing to both `iam.GroupRoles` and `iam.User`. 
- `primaryjoin`, `secondaryjoin` : Once secondary is determined, you can specify how you can map many side to the other. This is to define how you join the two. 
- `uselist` : Sometimes, the relationship is not necessarily `many to many` nor `one to many`. So, you can give `False` to uselist so it can refer to only one instance, if any.
- `collection_class` : Setting this value `set` or `list`, the relationship is put into the given set. The small detail about this is either set or list is not exactly the same as built-in version of them. 
- `innerjoin` : By default, relationship is joined using `outerjoin` which is for optional values that are mostly the case albeit with performance hit. If you are sure that the entities in relationship co-exist, you can give `True` to this. 

#### `eager_defaults`
If true, the ORM will fetch the value of server-generated values to the object, thereby obviating the need for `refresh`. The process is done by using backend's `RETURNING` inline or `SELECT` statement when the backend doesn't support it.<br>


#### `version_id_col`
This is to specify the column used for versioning. The purpose of versioning is to detect when two concurrent transactions are modifying the same row at roughly the same time. To grasp the true meaning of this, you have to also understand isolation level. In this proeject, it assumes the level being below `repeatable read`. This column ensures that all the updates are versioned by sending update query that looks like:<br>

```sql
UPDATE user SET version_id=:version_id, name=:name
WHERE user.id = :user_id AND user.version_id = :user_version_id
-- {"name": "new name", "version_id": 2, "user_id": 1, "user_version_id": 1}
```
The above UPDATE statement is updating the row that not only matches user.id = 1, it also is requiring that user.version_id = 1, where “1” is the last version identifier we’ve been known to use on this object. Note therefore that if you want to manage the value on application side, if you shouldn't fiddle with the version column, which is restrictive in a situation where you want to keep the record of all the version and some updates are sensitive to versioning while others are not. In this case, you need `version_id_generator`.

#### `version_id_generator` - Programmatic or Conditional Version Counters
When `version_id_generator` is set to False, we can programmatically set the version on our object. We can update our custom object without incrementing the version counter as well; the value of the counter will remain unchanged, and the UPDATE statement will still check against the previous value. This may be useful for schemes where only certain classes of UPDATE are sensitive to concurrency issues.<br>


### Unit Of Work
Unit of Work (UoW) pattern is our abstraction over the idea of atomic operations. It will allow us to fully decouple our service layer from infra-rlated concern. UOW collaboates with repositories we defined and each handler in service layer start a UOW as a context manager, the start of transaction.<br><br>

But what if you don't want to begin a transaction? Then you need different type of 


#### Autocommit vs transactional session
```python
#app.service_layer.unit_of_work
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_scoped_session,
    create_async_engine,
)

engine = create_async_engine(
    config.db_settings.get_uri(),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)
async_transactional_session = async_scoped_session(
    sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    scopefunc=current_task,
)
autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")

async_autocommit_session = async_scoped_session(
    sessionmaker(autocommit_engine, expire_on_commit=False, class_=AsyncSession),
    scopefunc=current_task,
)

DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY = async_transactional_session

```
Here we have `async_transactioanl_session` and `async_autocommit_session` despite its awfully confusing name, autocommit here means that the DBAPI does not use a transaction under any circumstances. For this reason, it is typical, though not strictly required, that a Session with AUTOCOMMIT isolation be used in a read-only fashion. 

#### SqlAlchemyUnitOfWork
```python
#app.service_layer.unit_of_work
class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=None):
        self.session_factory = (
            DEFAULT_SESSION_TRANSACTIONAL_SESSION_FACTORY
            if session_factory is None
            else session_factory
        )

    async def __aenter__(self):
        self.session: AsyncSession = self.session_factory()
        self.event_store: EventRepositoryProxy = EventRepositoryProxy(
            session=self.session,
        )

        self.users = weakref.proxy(self.event_store)
        self.groups = weakref.proxy(self.event_store)
        self.outboxes = OutboxRepository(model=OutBox, session=self.session)
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.rollback()
        await self.session.close()

    async def _commit(self):
        await self.session.commit()
```
You see that `SqlalchemyUnitOfWork` optionally takes default session if no factory is given. And async context manager `async def __aenter__` is defined, initializing `self.session`, `self.event_store`, and domain models. In this project, as only data stroage we have is RDBMS, we only need one type of UnitOfWork but if your project included heterogenous data stroages, you may consider implementing different kinds of UOWs. 


### Service Layer - handler
Handler is what provides public interface of your service and processes commands. It receives commands and start Unit of work, and invokes appropriate command methods given an aggregate.<br>
```python
class IAMService:
    @classmethod
    async def create_user(
        cls, msg: commands.CreateUser, *, uow: AbstractUnitOfWork
    ) -> UUID:
        async with uow:
            user = iam.User.create(msg)
            await uow.users.add(user)
            await uow.commit()
            return user.id

```


### Service Layer - messagebus
In MSA, what really matters is message. And message can be either event or command. Note that, however, event here does NOT mean that it is the same event as domain event. While domain event is contained strictly in one aggregate and service, in the context of MSA, contexts are supposed to be bounded to a certain subdomain, so events here mean either `event carried state transfer` or `notification`. In your service, it is expected that you have handlers for each of these messages and what messagebus does is basically taking the messages and dispatch them to appropriate handlers.<br>

```python
#app.service_layer.messagebus

class MessageBus:
    def __init__(
        self,
        event_handlers: dict[Type[DomainEvent], list[Callable]],
        command_handlers: dict[Type[Command], Callable],
        uow: Type[SqlAlchemyUnitOfWork] = SqlAlchemyUnitOfWork,
    ):
        self.uow = uow
        self.event_handlers = event_handlers
        self.command_handlers = command_handlers

    async def handle(
        self, message: Message
    ) -> deque[Any]:  # Return type need to be specified?
        queue: deque = deque([message])
        uow = self.uow()
        results: deque = deque()
        while queue:
            message = queue.popleft()
            logger.info("handling message %s", message.__class__.__name__)
            match message:
                case DomainEvent():
                    await self.handle_event(message, queue, results, uow)
                case Command():
                    cmd_result = await self.handle_command(message, queue, uow)
                    results.append(cmd_result)
                case _:
                    logger.error(f"{message} was not an Event or Command")
                    raise Exception
        return results


    async def handle_event(
        self,
        event: DomainEvent,
        queue: deque,
        results: deque,
        uow: SqlAlchemyUnitOfWork,
    ):
        for handler in self.event_handlers[type(event)]:
            try:
                logger.debug("handling event %s with handler %s", event, handler)
                res = (
                    await handler(event, uow=uow)
                    if getattr(handler, "uow_required", False)
                    else await handler(event)
                )

                # Handle only internal backlogs that should be handled within the bounded context
                queue.extend(uow.collect_backlogs(in_out="internal_backlogs"))

                # Normally, event is not supposed to return result but when it must, resort to the following.
                if res:
                    results.append(res)
            except StopSentinel as e:
                logger.error("%s", str(e))

                # If failover strategy is implemented even is appended
                if e.event:
                    queue.append(e.event)

                # Break the loop upon the reception of stop sentinel
                break
            except Exception as error:
                logger.exception(f"exception while handling event {str(error)}")

    async def handle_command(
        self, command: Command, queue: deque, uow: SqlAlchemyUnitOfWork
    ):
        logger.debug("handling command %s", command)
        try:
            handler = self.command_handlers[type(command)]
            res = (
                await handler(command, uow=uow)
                if getattr(handler, "uow_required", False)
                else await handler(command)
            )
            queue.extend(uow.collect_backlogs(in_out="internal_backlogs"))
            return res
        except Exception as e:
            logger.exception(f"exception while handling command {str(e)}")
            raise e

```
By design, your messagebus is instansiated somewhere and handle each messages using `handle` method. Inside the `handle` method, a deque is instantiated with the message you've gotten and while there is a message, it processes the message with two submethods, `handle_event` and `handle_command`, respectively. Finally it returns results back to caller that is mainly for command as it requires return value back to the client, which is not normally expected from the event handler. Essetianlly, that is what makes difference between event and command. While operations caused by both command and event expect changes to an aggregate, command expects return value back to client, which is not usually the case for event.<br><br>

Now, let's look at how event handlers and command handlers could be defined:<br>
```python
from app.domain import commands
from app.domain import events
EVENT_HANDLERS: dict = {
    events.UserCreated : [
            handlers.IAMService.notify_user_creation,
            handlers.IAMService.issue_promotion_token
            ]
}


COMMAND_HANDLERS: dict = {
    commands.CreateUser: handlers.IAMService.create_user,
    commands.RequestCreateGroup: handlers.IAMService.request_create_group,
}
```
Here comes yet another differences between command and event; while event may or may not be mapped to list of handlers, command is mapped to only one handler. So, events are raised as a spin-off of command. 


### Bootstrapping - Manual DI
Declaring an explicit dependency is an example of DIP - rather than having implicit dependencies on **specific** detail by having module import, we want to have an explicit dependency on **abstraction**. That is to say, instead of having a program like:
```python
from . import send_email

def send_out_notification(event: events.TransactionCleared):
    send_email("migo@mail.com","Hello")
    ...
```

We want to have something like this:

```python
def send_out_notification(event:events.TransactionCleared,send_mail:Callble):
    send_mail("migo@mail.com","Hello")
```
What it enables is basically choosing the dpenendency we want depending on environemnt(e.g., test environement), and avoiding a violation of the single responsibility principle(SRP). Here, we reach for a parttern called `Composition Root` that is a bootstrap script, and we'll do a bit of Manual DI(dependency injection without a framework).<br><br>

Introducing this pattern means your entrypoints initialize bootstrapper so it can prepare handlers with injected dependencies, and pass the dependency-injected hanlders to messagebus.<br>

#### Initialization

```python
#app.bootstrap

class Bootstrap:
    def __init__(
        self,
        uow: Type[
            unit_of_work.SqlAlchemyUnitOfWork
        ] = unit_of_work.SqlAlchemyUnitOfWork,
        event_handlers: dict | None = None,
        command_handlers: dict | None = None,
        **kwargs,  # accept kwargs for testability
    ):
        self.uow = uow

        self.event_handlers = (
            event_handlers if event_handlers is not None else copy(EVENT_HANDLERS)
        )
        self.command_handlers = (
            command_handlers if command_handlers is not None else copy(COMMAND_HANDLERS)
        )
        self.dependencies = {k: v for k, v in kwargs.items()}

```
As bootstrap is what loads and inject dependencies into handlers, Bootstrap itself should be initialize when program boots up. It means that it should be at the top level of the project.<br><br>

When initialized, both `even_handlers` and `command_handlers` are optioanlly passed for the sake of testability. See the following:
```python
#test_bootstrapper.py

@pytest.mark.asyncio
async def test_bootstrapper():
    ...

    bootstrap = Bootstrap(
        command_handlers={TestCommand: FakeService.test_command},
        event_handlers={TestEvent: [FakeService.test_event]},
        injected_func=injectable_func,
    )
    ...
```
As you can see, by optionally taking handler arguments, you can test out if bootstrap itself works according to what you need it for.

#### Invoking Bootstrapper
```python

class Bootstrap:
    ...


    def __call__(self):
        # dependencies: dict = {}
        injected_event_handlers = {
            event_type: [
                inject_dependencies(handler, self.dependencies)
                for handler in listed_handlers
            ]
            for event_type, listed_handlers in self.event_handlers.items()
        }
        injected_command_handlers = {
            command_type: inject_dependencies(handler, self.dependencies)
            for command_type, handler in self.command_handlers.items()
        }

        return MessageBus(
            uow=self.uow,
            event_handlers=injected_event_handlers,
            command_handlers=injected_command_handlers,
        )
    ...

```

After the initialization, you can invoke `__call__` method as per your need and it returns initialized `MessageBus` object with dependency injected handlers. The dependency injection could be simply making lambda or creating function capturing the variable using closure, using `inject_dependencies`.<br>

#### `inject_dependencies`

```python
def inject_dependencies(handler, dependencies: dict) -> Callable:
    params = inspect.signature(handler).parameters
    deps = {
        name: dependency for name, dependency in dependencies.items() if name in params
    }

    # Create function dynamically
    return render_injected_function(handler=handler, **deps)


def render_injected_function(handler, **kwrags) -> Callable:
    func = partial(handler, **kwrags)
    setattr(func, "uow_required", handler.uow_required)
    return func

```
What the listed functions do is taking function signatures and create dependencies, and return injected function. 

