from app.greet import greet


def test_greets_by_name() -> None:
    assert greet("Ada") == "Hello Ada!"


def test_greets_anonymous() -> None:
    assert greet("") == "Hello there!"
