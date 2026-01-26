"""Type definitions for Kumo Cloud integration (Optimization 7)."""

from __future__ import annotations

from typing import TypedDict, NotRequired


class DeviceModel(TypedDict):
    """Device model information."""

    materialDescription: NotRequired[str]
    serialProfile: NotRequired[str]


class DeviceAdapter(TypedDict):
    """Device adapter information."""

    deviceSerial: str
    roomTemp: NotRequired[float]
    operationMode: NotRequired[str]
    power: NotRequired[int]
    fanSpeed: NotRequired[str]
    airDirection: NotRequired[str]
    spCool: NotRequired[float]
    spHeat: NotRequired[float]
    humidity: NotRequired[int]
    connected: NotRequired[bool]


class Zone(TypedDict):
    """Zone information."""

    id: str
    name: NotRequired[str]
    adapter: NotRequired[DeviceAdapter]


class DeviceDetail(TypedDict):
    """Device detail information."""

    serialNumber: NotRequired[str]
    model: NotRequired[DeviceModel]
    roomTemp: NotRequired[float]
    operationMode: NotRequired[str]
    power: NotRequired[int]
    fanSpeed: NotRequired[str]
    airDirection: NotRequired[str]
    spCool: NotRequired[float]
    spHeat: NotRequired[float]
    humidity: NotRequired[int]
    connected: NotRequired[bool]
    updatedAt: NotRequired[str]


class MinimumSetPoints(TypedDict):
    """Minimum temperature setpoints."""

    heat: NotRequired[float]
    cool: NotRequired[float]


class MaximumSetPoints(TypedDict):
    """Maximum temperature setpoints."""

    heat: NotRequired[float]
    cool: NotRequired[float]


class DeviceProfile(TypedDict):
    """Device profile capabilities."""

    numberOfFanSpeeds: NotRequired[int]
    hasVaneSwing: NotRequired[bool]
    hasVaneDir: NotRequired[bool]
    hasModeHeat: NotRequired[bool]
    hasModeDry: NotRequired[bool]
    hasModeVent: NotRequired[bool]
    minimumSetPoints: NotRequired[MinimumSetPoints]
    maximumSetPoints: NotRequired[MaximumSetPoints]


class TokenResponse(TypedDict):
    """Token response from API."""

    access: str
    refresh: str


class LoginResponse(TypedDict):
    """Login response from API."""

    token: TokenResponse


class Site(TypedDict):
    """Site information."""

    id: str
    name: str
