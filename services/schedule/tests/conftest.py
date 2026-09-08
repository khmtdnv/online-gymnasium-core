from typing import Never

import pytest

from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory


@pytest.fixture
def unused_uow_factory() -> UnitOfWorkFactory:
    def factory() -> Never:
        raise AssertionError("This test must not create a UnitOfWork")

    return factory
