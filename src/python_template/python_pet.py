class PythonPet:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.hunger: int = 5  # Scale of 0 (full) to 10 (starving).
        self.happiness: int = 5  # Scale of 0 (sad) to 10 (happy).

    def feed(self) -> None:
        """Reduce hunger level."""
        if self.hunger > 0:
            self.hunger -= 1

    def play(self) -> None:
        """Increase happiness level."""
        if self.happiness < 10:
            self.happiness += 1

    def get_status(self) -> str:
        """
        Return status report.

        :returns: Status report
        """
        return f"{self.name} - Hunger: {self.hunger}, Happiness: {self.happiness}"


def main() -> None:
    python_pet = PythonPet("Baby Python")
    print(python_pet.get_status())


if __name__ == "__main__":
    main()
