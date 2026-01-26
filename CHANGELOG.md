# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-01-25

### Performance Improvements
- **Parallel Zone Fetching**: Device data for all zones now fetched concurrently instead of sequentially
  - Reduces initial load time by up to 3x for multi-zone setups
  - Example: 3 zones now load in ~2 seconds instead of ~6 seconds
- **Optimistic State Cleanup**: Improved efficiency using dictionary comprehension instead of two-pass iteration
  - Reduces memory allocation and improves response time during state updates
- **Profile Data Normalization**: Profile data now normalized once via property instead of 8+ times per update
  - Eliminates repeated type checks and lookups throughout entity lifecycle

### Reliability Improvements
- **Cache Memory Leak Prevention**: Automatic cleanup of cached commands older than 5 minutes
  - Prevents unbounded memory growth in long-running Home Assistant installations
  - Handles edge cases where devices go offline or API stops returning timestamps
- **Token Persistence**: Refreshed authentication tokens now persisted to config entry
  - Reduces re-authentication requirements after Home Assistant restarts
  - Fewer API calls to authentication endpoints
  - Improved reliability across restarts

### Code Quality Improvements
- **Type Safety with TypedDict**: Added comprehensive type definitions for all API responses
  - Better IDE autocomplete and type checking
  - Self-documenting API structure
  - Catches type-related bugs earlier in development
- **Rate Limiting Refactor**: Extracted rate limiting logic to dedicated async context manager
  - More testable and maintainable code
  - Cleaner separation of concerns
  - Reusable pattern for future API clients
- **Reduced Debug Logging**: Eliminated excessive logging in cache culling operations
  - Cleaner log files for actual debugging
  - Reduced I/O overhead from logging

### Technical Details
- New file: `types.py` for TypedDict definitions
- Modified files: `api.py`, `coordinator.py`, `climate.py`, `__init__.py`

## [2.0.0] - 2026-01-25

### Added
- Support for units that report `autoHeat` or `autoCool` operation modes
- HVACMode.HEAT_COOL now activates when these modes are reported
- Granular fan and vane control with user-friendly labels
- Optimistic UI updates for immediate feedback
- Temperature and humidity sensor entities
- Command caching with timestamps to prevent state bouncing
- Immediate status refresh after sending commands
- Rate limiting to prevent API 429 errors (2-second minimum interval between requests)
- Retry logic with exponential backoff for failed API requests

### Fixed
- Temperature synchronization issue when Home Assistant is configured to display Fahrenheit
  - Added temperature snapping to 0.5°C increments before sending to API
  - Ensures consistent temperature readings across HA, MHK2 thermostats, and Comfort Cloud app
  - Resolves issue where unsnapped Celsius conversions (e.g., 18.8889°C for 66°F) caused mismatches
- Multiple sites configuration issue
- State bouncing issue where UI would revert to old state before updating with new value
- Improved responsiveness by caching commands until API confirms changes

### Changed
- Moved coordinator logic to separate coordinator.py module for better organization
- Enhanced command handling with automatic cache culling based on API update timestamps

## [1.0.0] - 2024-01-01

### Added
- Initial release of Mitsubishi Comfort integration
- Climate control support for Mitsubishi Electric systems via Kumo Cloud API
- Config flow for easy setup
- Multi-zone support
- Automatic token refresh
- Device capability detection
- Support for temperature, HVAC modes, fan speeds, and air direction
- Real-time temperature and humidity monitoring

### Features
- Climate entity with full Home Assistant integration
- Automatic discovery of zones within selected site
- Configurable update intervals
- Error handling and retry logic
- Support for multiple HVAC modes (heat, cool, dry, fan, auto)
- Device-specific feature detection 