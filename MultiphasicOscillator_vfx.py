"""
MULTI-PHASIC OSCILLATOR — FL Studio VFX Script

A transport-synchronised bank of phase-offset sine LFOs.  It exposes eight
normalised controller outputs (Oscillator 1–8), suitable for linking to native
or third-party generator/effect parameters in Patcher.

INSTALLATION
1. In Patcher, add VFX Script and open its Script tab.
2. Paste this file's contents into the tab, then reload/run the script.
3. Connect VFX Script's Automation outputs to the target plug-in parameters.
   Use only as many outputs as selected by Oscillator Count.

Output values are bipolar sine waves converted to FL's normalised 0–1 range:
0.0 = trough, 0.5 = centre, 1.0 = peak.

Each output has its own Scale and Offset. Scale changes modulation depth;
Offset moves the waveform's centre point. Both are applied after the oscillator
waveform has been calculated.

The cycle length is expressed in quarter notes: 16 is four 4/4 bars, 4 is one
4/4 bar, and 1 is one beat.  By default the script uses the song position. Turn
off Use Song Time to use a free-running PPQ clock that continues through
playlist loop restarts.
"""

import math
import flvfx as vfx

MAX_OSCILLATORS = 8
OUTPUT_NAMES = ["Oscillator " + str(index) for index in range(1, MAX_OSCILLATORS + 1)]


class OscillatorState:
    """Stores the compensation required for click-free reverse toggling."""

    def __init__(self):
        self.reverse = False
        self.reverse_phase_offset = 0.0
        self.clock_ticks = 0

    def reset(self):
        self.reverse = False
        self.reverse_phase_offset = 0.0
        self.clock_ticks = 0


state = OscillatorState()


def clamp(value, low, high):
    return max(low, min(high, value))


def input_value(name):
    """Read a control in the Oscillator group."""
    return vfx.context.form.getInputValue("Oscillator: " + name)


def output_input_value(output_name, name):
    """Read a per-output control from its output group."""
    return vfx.context.form.getInputValue(output_name + ": " + name)


def calculate_outputs(quarter_notes, phase_offset, cycle_length, rate_mult,
                      oscillator_count, spread, tension, invert, reverse):
    """Return bipolar values (-1 to +1) for the requested oscillator count."""
    cycle_length = max(0.0625, cycle_length)
    rate_mult = max(0.0, rate_mult)
    tension = max(0.01, tension)
    oscillator_count = max(1, min(MAX_OSCILLATORS, int(oscillator_count)))

    raw_theta = ((quarter_notes / cycle_length) * rate_mult + phase_offset) * (2.0 * math.pi)

    # Preserve the current waveform position the instant direction changes.
    if reverse != state.reverse:
        state.reverse_phase_offset = -2.0 * raw_theta - state.reverse_phase_offset
        state.reverse = reverse

    if reverse:
        master_theta = -(raw_theta + state.reverse_phase_offset)
    else:
        master_theta = raw_theta + state.reverse_phase_offset

    angle_step = (2.0 * math.pi) / oscillator_count
    centre_angle = ((oscillator_count - 1) * angle_step) / 2.0
    master_sin = math.sin(master_theta)
    master_cos = math.cos(master_theta)
    values = []

    for index in range(oscillator_count):
        base_offset = index * angle_step - centre_angle
        direction = -1.0 if invert and index % 2 == 0 else 1.0
        angle_offset = base_offset + base_offset * (spread - 1.0) * direction

        # sin(master_theta + angle_offset), using the angle-addition identity.
        value = master_sin * math.cos(angle_offset) + master_cos * math.sin(angle_offset)

        # At > 1 peaks are held longer; at < 1 the curve stays nearer centre.
        if tension != 1.0:
            value = math.copysign(abs(value) ** (1.0 / tension), value)
        values.append(value)

    return values


def onTick():
    """Update controller outputs on every FL Studio timing tick."""
    enabled = input_value("Enable")
    oscillator_count = int(input_value("Oscillator Count"))

    # Stopped transport returns both timing modes to the first sample, making
    # the next playback start deterministic.
    if not vfx.context.isPlaying:
        state.reset()

    if not enabled:
        for output_name in OUTPUT_NAMES:
            vfx.setOutputController(output_name, 0.5)
        return

    use_song_time = bool(input_value("Use Song Time"))
    if use_song_time:
        # Song position: restarting a Playlist loop restarts the oscillator
        # from the phase at that timeline position.
        quarter_notes = float(vfx.context.ticks) / float(vfx.context.PPQ)
    else:
        # Free-running clock: every VFX timing callback advances one PPQ tick.
        # Unlike context.ticks, this counter never moves backwards at a loop
        # boundary, so the waveform remains continuous across short loops.
        quarter_notes = float(state.clock_ticks) / float(vfx.context.PPQ)
        state.clock_ticks += 1
    outputs = calculate_outputs(
        quarter_notes=quarter_notes,
        phase_offset=input_value("Phase Offset"),
        cycle_length=input_value("Cycle Length"),
        rate_mult=input_value("Rate Multiplier"),
        oscillator_count=oscillator_count,
        spread=input_value("Spread"),
        tension=input_value("Tension"),
        invert=bool(input_value("Invert Even Oscillators")),
        reverse=bool(input_value("Reverse Direction")),
    )

    # Per-output Scale changes the bipolar modulation depth. Offset moves the
    # centre point in normalised controller units (-0.5 to +0.5).
    for index, output_name in enumerate(OUTPUT_NAMES):
        bipolar_value = outputs[index] if index < len(outputs) else 0.0
        scale = output_input_value(output_name, "Scale")
        offset = output_input_value(output_name, "Offset")
        output_value = 0.5 + offset + 0.5 * bipolar_value * scale
        vfx.setOutputController(output_name, clamp(output_value, 0.0, 1.0))


def createDialog():
    description = (
        "Multi-Phasic Oscillator. Generates up to eight transport-synchronised "
        "sine LFOs with evenly distributed phases. Outputs are normalised: "
        "0.5 is the centre value."
    )
    form = vfx.ScriptDialog("Multi-Phasic Oscillator", description)
    form.addGroup("Oscillator")
    form.addInputCheckbox("Enable", 1, hint="When off, every output is held at 0.5.")
    form.addInputKnob("Phase Offset", 0.0, 0.0, 1.0,
                      hint="Adds a global phase offset. One equals a full cycle.")
    form.addInputKnob("Cycle Length", 16.0, 0.0625, 64.0,
                      hint="Length of one full cycle, in quarter notes. 16 = four bars in 4/4.")
    form.addInputCheckbox("Use Song Time", 1,
                          hint="On: phase follows the Playlist position. Off: phase runs based on real world clock.")
    form.addInputKnob("Rate Multiplier", 1.0, 0.0, 8.0,
                      hint="Speed multiplier applied to the transport-synchronised phase.")
    form.addInputKnobInt("Oscillator Count", 6, 1, MAX_OSCILLATORS,
                         hint="Number of active outputs, starting at Oscillator 1.")
    form.addInputKnob("Spread", 1.0, 0.0, 6.0,
                      hint="1 = even phase spacing; other values expand or contract offsets.")
    form.addInputKnob("Tension", 1.0, 0.1, 3.0,
                      hint="1 = sine; higher values hold closer to peaks and troughs.")
    form.addInputCheckbox("Invert Even Oscillators", 0,
                          hint="Flips the spread direction for Oscillators 1, 3, 5 and 7.")
    form.addInputCheckbox("Reverse Direction", 0,
                          hint="Run backwards without a phase jump when toggled.")
    form.endGroup()

    form.addGroup("Output scaling")
    for output_name in OUTPUT_NAMES:
        # ScriptDialog uses groups as its UI sections. These eight sections are
        # deliberately separate: the public VFX Script form API does not
        # document a reliable nested-group hierarchy.
        form.addGroup(output_name)
        form.addInputKnob("Scale", 1.0, 0.0, 1.0,
                          hint="Modulation depth for " + output_name + ".")
        form.addInputKnob("Offset", 0.0, -0.5, 0.5,
                          hint="Centre shift for " + output_name + " in normalised output units.")
        form.endGroup()
        vfx.addOutputController(output_name, 0.5)
    return form
    form.endGroup()
