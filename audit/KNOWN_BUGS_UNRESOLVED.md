# Known Bugs Unresolved / Partially Verified

* **BUG-003**: Microphone / Real Audio Hardware Pipeline
  - **Status**: PARTIALLY VERIFIED
  - **Forensic Reason**: While asynchronous audio capture, PyAudio backend fallback, silence thresholding, and TTS synthesis routines pass 100% in programmatic and mock test suites, Rule 0.21 strictly dictates:
    > "Do not claim microphone support if a real microphone→STT→reasoning→TTS→speaker test has not completed."
  - **Limitation**: The current execution context is headless/automated and lacks active physical acoustic transducers (physical microphone input and physical speaker feedback).
  - **Requirement for PASS**: A human operator or physical hardware rig must execute an acoustic round-trip test on a real desktop workstation.
