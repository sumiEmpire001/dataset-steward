# Embedded C++ companion

Bounded numeric sensor-cell quality gate with missing, invalid and range states. Does not replace Python's CSV, Decimal, duplicate grouping or reversible cleaning. Floating-point precision differs from Python Decimal.

## Host verification

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
python -m unittest discover -s tests -v
```

The C++11 header is allocation-free and uses no Arduino-specific APIs. Integrators may include `cpp/include/EmbeddedCore.h` in Arduino Uno or ESP32 sketches, but **firmware builds and physical-board tests are not yet verified**. Use advisory LEDs only; never directly switch mains, motors or safety-critical actuators. Handle sensor disconnection, time rollover, watchdog resets, retained configuration and electrical isolation separately. CI verifies host C++ and existing Python tests, not device behavior.
