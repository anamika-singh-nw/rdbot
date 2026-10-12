import pytest

from navigator.safety import screen

EMERGENCIES = [
    "my father has crushing chest pain and is sweating",
    "she can't breathe properly",
    "his face is drooping and his speech is slurred",
    "my son had a seizure",
    "I want to end my life",
    "I keep thinking about ending my life",
    "sometimes I just want to die",
    "I don't want to live anymore",
    "my daughter has been cutting herself",
    "he says everyone would be better off dead without him",
    "my 3 week old has a fever",
    "she is vomiting blood",
]
ROUTINE = [
    "my son has ear pain, Saturdays only",
    "need a dermatologist in Whitefield",
    "follow-up for my knee, no chest pain or breathlessness",
    "is the benefit of physiotherapy covered?",
    "book an appointment for treatment of acne",
    "my mother's life has been hard since the knee surgery",
    "end of the week works best for me",
]


@pytest.mark.parametrize("msg", EMERGENCIES)
def test_emergencies_are_caught(msg):
    assert screen(msg) is not None


@pytest.mark.parametrize("msg", ROUTINE)
def test_routine_requests_pass(msg):
    assert screen(msg) is None


def test_self_harm_gets_crisis_line_not_ambulance():
    _, reply = screen("I keep thinking about suicide")
    assert "14416" in reply
