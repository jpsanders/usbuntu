from python_template.python_pet import PythonPet


class TestPythonPet:
    def test_python_pet(self) -> None:
        python_pet = PythonPet("Baby Python")

        assert python_pet.hunger == 5
        assert python_pet.happiness == 5

        python_pet.feed()
        assert python_pet.hunger == 4  # Hunger should decrease.

        python_pet.play()
        assert python_pet.happiness == 6  # Happiness should increase.

        status = python_pet.get_status()
        assert "Baby Python" in status
        assert "Hunger: 4" in status
        assert "Happiness: 6" in status
