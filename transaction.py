"""Snapshot and conservatively roll back datablocks made during one import."""

from __future__ import annotations

from dataclasses import dataclass

import bpy


_COLLECTIONS = (
    "objects",
    "collections",
    "meshes",
    "armatures",
    "materials",
    "images",
    "node_groups",
    "actions",
)

_LABELS = {
    "actions": "action",
    "meshes": "mesh",
    "armatures": "armature",
    "materials": "material",
    "images": "image",
    "node_groups": "node group",
}


@dataclass(frozen=True)
class DataSnapshot:
    """Identity snapshot of datablocks that predate an import attempt."""

    items: dict[str, frozenset[object]]

    @classmethod
    def capture(cls) -> "DataSnapshot":
        return cls({name: frozenset(getattr(bpy.data, name)) for name in _COLLECTIONS})

    def added(self, collection_name: str) -> set[object]:
        return set(getattr(bpy.data, collection_name)) - set(self.items[collection_name])


@dataclass
class RollbackReport:
    removed: list[str]
    retained: list[str]


class ImportTransaction:
    """Own a pre-import snapshot and remove only post-snapshot datablocks."""

    def __init__(self) -> None:
        self.before = DataSnapshot.capture()

    def added(self, collection_name: str) -> set[object]:
        return self.before.added(collection_name)

    @property
    def new_objects(self) -> set[bpy.types.Object]:
        return self.added("objects")

    @staticmethod
    def _is_current(data_collection, datablock: object) -> bool:
        """Avoid deleting a replacement datablock that happens to share a name."""
        return data_collection.get(datablock.name) is datablock

    def _unlink_new_collection(self, collection: bpy.types.Collection) -> None:
        """Detach a newly-created collection without changing pre-existing parents."""
        for scene in bpy.data.scenes:
            if scene.collection.children.get(collection.name) is collection:
                scene.collection.children.unlink(collection)
        for parent in bpy.data.collections:
            if parent is not collection and parent.children.get(collection.name) is collection:
                parent.children.unlink(collection)

    def rollback(self) -> RollbackReport:
        """Remove only data created since the snapshot, in safe dependency order."""
        removed: list[str] = []
        retained: list[str] = []

        for obj in list(self.added("objects")):
            if not self._is_current(bpy.data.objects, obj):
                continue
            name = obj.name
            bpy.data.objects.remove(obj, do_unlink=True)
            removed.append(f"object: {name}")

        for collection in list(self.added("collections")):
            if not self._is_current(bpy.data.collections, collection):
                continue
            self._unlink_new_collection(collection)
            if collection.users == 0:
                name = collection.name
                bpy.data.collections.remove(collection)
                removed.append(f"collection: {name}")
            else:
                retained.append(f"collection still in use: {collection.name}")

        for collection_name in ("actions", "meshes", "armatures", "materials", "images", "node_groups"):
            data_collection = getattr(bpy.data, collection_name)
            label = _LABELS[collection_name]
            for datablock in list(self.added(collection_name)):
                if not self._is_current(data_collection, datablock):
                    continue
                if datablock.users == 0:
                    name = datablock.name
                    data_collection.remove(datablock)
                    removed.append(f"{label}: {name}")
                else:
                    retained.append(f"{label} still in use: {datablock.name}")
        return RollbackReport(removed=removed, retained=retained)
