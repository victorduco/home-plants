"""Isolated regressions for the version-controlled Govee scene-cache overlay."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import time
import types
import unittest


def _load_overlay() -> types.ModuleType:
    """Import the overlay without importing Home Assistant or Govee packages."""
    package = "_govee_scene_hotfix_test"
    package_module = types.ModuleType(package)
    package_module.__path__ = []
    api_package = types.ModuleType(f"{package}.api")
    api_package.__path__ = []
    models_package = types.ModuleType(f"{package}.models")
    models_package.__path__ = []

    client_module = types.ModuleType(f"{package}.api.client")
    client_module.GoveeApiClient = object
    exceptions_module = types.ModuleType(f"{package}.api.exceptions")

    class GoveeApiError(Exception):
        """Test stand-in for the integration exception."""

    exceptions_module.GoveeApiError = GoveeApiError
    device_module = types.ModuleType(f"{package}.models.device")
    device_module.GoveeDevice = object

    sys.modules.update(
        {
            package: package_module,
            f"{package}.api": api_package,
            f"{package}.api.client": client_module,
            f"{package}.api.exceptions": exceptions_module,
            f"{package}.models": models_package,
            f"{package}.models.device": device_module,
        }
    )

    source = (
        Path(__file__).resolve().parents[1]
        / "ha"
        / "patches"
        / "govee-scene-cache-hotfix"
        / "scene_cache.py"
    )
    spec = importlib.util.spec_from_file_location(f"{package}.scene_cache", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load overlay: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HOTFIX = _load_overlay()
DEVICE = types.SimpleNamespace(name="Test Light", sku="H0001")


class ImmediateApi:
    """API fixture proving successful scene data remains unchanged."""

    def __init__(self) -> None:
        self.dynamic = [{"name": "Aurora", "sceneId": 1}]
        self.diy = [{"name": "My DIY", "sceneId": 2}]

    async def get_dynamic_scenes(self, device_id: str, sku: str) -> list[dict]:
        return self.dynamic

    async def get_diy_scenes(self, device_id: str, sku: str) -> list[dict]:
        return self.diy


class BlockingApi:
    """One shared dynamic-scene request controlled by the test."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.cancelled = False

    async def get_dynamic_scenes(self, device_id: str, sku: str) -> list[dict]:
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return [{"name": "Shared"}]


class DualBlockingApi:
    """Independent dynamic and DIY requests for timeout/shutdown tests."""

    def __init__(self) -> None:
        self.dynamic_started = asyncio.Event()
        self.diy_started = asyncio.Event()
        self.dynamic_calls = 0
        self.diy_calls = 0
        self.dynamic_cancelled = False
        self.diy_cancelled = False

    async def get_dynamic_scenes(self, device_id: str, sku: str) -> list[dict]:
        self.dynamic_calls += 1
        self.dynamic_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.dynamic_cancelled = True
            raise

    async def get_diy_scenes(self, device_id: str, sku: str) -> list[dict]:
        self.diy_calls += 1
        self.diy_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.diy_cancelled = True
            raise


class SceneCacheHotfixTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_keeps_dynamic_and_diy_functionality(self) -> None:
        api = ImmediateApi()
        manager = HOTFIX.SceneCacheManager(api, fetch_timeout=0.5)

        dynamic = await manager.async_get_scenes("device", DEVICE)
        diy = await manager.async_get_diy_scenes("device", DEVICE)
        await asyncio.sleep(0)

        self.assertIs(dynamic, api.dynamic)
        self.assertIs(diy, api.diy)
        self.assertIs(manager._scene_cache["device"][1], api.dynamic)
        self.assertIs(manager._diy_scene_cache["device"][1], api.diy)
        self.assertEqual(manager._scene_inflight, {})
        self.assertEqual(manager._diy_scene_inflight, {})

    async def test_cancelled_waiter_cannot_cancel_or_unlink_shared_task(self) -> None:
        api = BlockingApi()
        manager = HOTFIX.SceneCacheManager(api, fetch_timeout=1.0)

        first_waiter = asyncio.create_task(
            manager.async_get_scenes("device", DEVICE, refresh=True)
        )
        await asyncio.wait_for(api.started.wait(), timeout=0.5)
        shared_task = manager._scene_inflight["device"]
        second_waiter = asyncio.create_task(
            manager.async_get_scenes("device", DEVICE, refresh=True)
        )
        await asyncio.sleep(0)

        first_waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first_waiter

        self.assertFalse(api.cancelled)
        self.assertFalse(shared_task.done())
        self.assertIs(manager._scene_inflight["device"], shared_task)
        self.assertEqual(api.calls, 1)

        api.release.set()
        result = await asyncio.wait_for(second_waiter, timeout=0.5)
        await asyncio.sleep(0)

        self.assertEqual(result, [{"name": "Shared"}])
        self.assertEqual(api.calls, 1)
        self.assertNotIn("device", manager._scene_inflight)

    async def test_deadline_returns_stale_without_overwriting_cache(self) -> None:
        api = DualBlockingApi()
        manager = HOTFIX.SceneCacheManager(api, fetch_timeout=0.02)
        scene_entry = (time.monotonic() - 1000, [{"name": "Old scene"}])
        diy_entry = (time.monotonic() - 1000, [{"name": "Old DIY"}])
        manager._scene_cache["device"] = scene_entry
        manager._diy_scene_cache["device"] = diy_entry

        started_at = asyncio.get_running_loop().time()
        with self.assertLogs(HOTFIX.__name__, level="ERROR"):
            dynamic, diy = await asyncio.wait_for(
                asyncio.gather(
                    manager.async_get_scenes("device", DEVICE, refresh=True),
                    manager.async_get_diy_scenes("device", DEVICE, refresh=True),
                ),
                timeout=0.5,
            )
        elapsed = asyncio.get_running_loop().time() - started_at
        await asyncio.sleep(0)

        self.assertLess(elapsed, 0.5)
        self.assertIs(dynamic, scene_entry[1])
        self.assertIs(diy, diy_entry[1])
        self.assertIs(manager._scene_cache["device"], scene_entry)
        self.assertIs(manager._diy_scene_cache["device"], diy_entry)
        self.assertTrue(api.dynamic_cancelled)
        self.assertTrue(api.diy_cancelled)
        self.assertEqual(api.dynamic_calls, 1)
        self.assertEqual(api.diy_calls, 1)
        self.assertEqual(manager._scene_inflight, {})
        self.assertEqual(manager._diy_scene_inflight, {})

    async def test_identity_cleanup_cannot_remove_replacement_task(self) -> None:
        manager = HOTFIX.SceneCacheManager(ImmediateApi(), fetch_timeout=0.5)
        completed = asyncio.create_task(asyncio.sleep(0, result=[]))
        await completed
        blocker = asyncio.Event()
        replacement = asyncio.create_task(blocker.wait())
        inflight = {"device": replacement}

        manager._cleanup_inflight(inflight, "device", completed)
        self.assertIs(inflight["device"], replacement)

        replacement.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await replacement

    async def test_shutdown_cancels_and_awaits_both_catalogue_tasks(self) -> None:
        api = DualBlockingApi()
        manager = HOTFIX.SceneCacheManager(api, fetch_timeout=10.0)
        scene_waiter = asyncio.create_task(
            manager.async_get_scenes("device", DEVICE, refresh=True)
        )
        diy_waiter = asyncio.create_task(
            manager.async_get_diy_scenes("device", DEVICE, refresh=True)
        )
        await asyncio.wait_for(
            asyncio.gather(
                api.dynamic_started.wait(),
                api.diy_started.wait(),
            ),
            timeout=0.5,
        )

        await asyncio.wait_for(manager.async_shutdown(), timeout=0.5)
        outcomes = await asyncio.gather(
            scene_waiter,
            diy_waiter,
            return_exceptions=True,
        )

        self.assertTrue(
            all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes)
        )
        self.assertTrue(api.dynamic_cancelled)
        self.assertTrue(api.diy_cancelled)
        self.assertEqual(manager._scene_inflight, {})
        self.assertEqual(manager._diy_scene_inflight, {})


if __name__ == "__main__":
    unittest.main()
