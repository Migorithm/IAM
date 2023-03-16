from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Type
from uuid import UUID, uuid4

from ..events import domain_event
from .. import resolver


@dataclass
class Aggregate:
    """
    Base Class For Aggregate.
    """

    # Exceptions
    class NotAggregateError(Exception):
        pass

    class VersionError(Exception):
        pass

    # Events For Base Aggregate
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
            kwargs.pop("externally_notifiable")
            kwargs.pop("internally_notifiable")
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

    def _trigger_(
        self,
        event_class: Type["Aggregate.Event"],
        **kwargs,
    ) -> None:
        """
        Triggers domain event of given type,
        extending the sequence of domain events for this aggregate object
        """
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

    id: UUID
    version: int
    create_dt: datetime
    update_dt: datetime = field(init=False)
    events: deque[Event] = field(init=False)

    def __post_init__(self):
        self.events = deque()
