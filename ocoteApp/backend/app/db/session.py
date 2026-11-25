from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


@contextmanager
def unit_of_work(session: Session) -> Iterator[Session]:
    with session.begin():
        yield session
