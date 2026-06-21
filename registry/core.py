from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from .spec import ComponentSpec

T = TypeVar("T")


# class ComponentRegistry<T> {...}
class ComponentRegistry(Generic[T]):
    def __init__(self, category: str) -> None:
        self.category = category
        # name -> component class/factory: calling it creates a T instance
        self._components: dict[str, Callable[..., T]] = {}

    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        # validate and record the component, then return it unchanged
        def decorator(component: Callable[..., T]) -> Callable[..., T]:
            if name in self._components:
                raise ValueError(f"{self.category} component already registered: {name}")
            self._components[name] = component
            return component

        # return the decorator that will be applied after the component is created
        return decorator

    # `/` makes `name` positional-only; `**options: object` means `options` is dict[str, object]
    def create(self, name: str, /, **options: object) -> T:
        try:
            component = self._components[name]
        except KeyError as error:
            available = ", ".join(sorted(self._components)) or "none"
            raise KeyError(f"unknown {self.category} component: {name}; available: {available}") from error
        return component(**options)

    def create_spec(self, spec: ComponentSpec) -> T:
        return self.create(spec.name, **dict(spec.options))

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._components))
