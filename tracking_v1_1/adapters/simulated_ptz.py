from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SimulatedPTZCommand:
    pan: str
    tilt: str
    speed: float


@dataclass
class SimulatedPTZAdapter:
    """
    POC-only PTZ adapter.

    This adapter never talks to physical camera hardware.
    It records and prints the simulated PTZ commands so the
    complete follow-control loop can be demonstrated safely.
    """

    last_command: SimulatedPTZCommand | None = None
    history: list[SimulatedPTZCommand] = field(default_factory=list)

    def move(self, pan: str, tilt: str, speed: float) -> SimulatedPTZCommand:
        command = SimulatedPTZCommand(
            pan=pan,
            tilt=tilt,
            speed=float(speed),
        )

        self.last_command = command
        self.history.append(command)

        print(
            f"SIM PTZ: pan={command.pan}, "
            f"tilt={command.tilt}, "
            f"speed={command.speed:.2f}"
        )

        return command

    def stop(self) -> SimulatedPTZCommand:
        command = SimulatedPTZCommand(
            pan="STOP",
            tilt="STOP",
            speed=0.0,
        )

        self.last_command = command
        self.history.append(command)

        print("SIM PTZ: STOP")

        return command

    def reset(self) -> None:
        self.last_command = None
        self.history.clear()