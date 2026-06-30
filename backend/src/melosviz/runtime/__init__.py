"""Runtime adapters — headless generators for each pro-tool renderer.

Sub-packages
------------
* :mod:`melosviz.runtime.touchdesigner` — TouchDesigner .toe project
  generator + OSC/WebSocket bridge + override round-trip.

The conductor adapter registry keys used here:

``live_stage``
    Primary live-performance path: TouchDesigner runtime + NDI/Spout output.
"""
