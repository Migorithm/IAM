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
Here, you can see that `User` is an aggregate that inherit `Aggregate` abstract class and its `create()` method calls for its super class's `_create_()`.<br>


