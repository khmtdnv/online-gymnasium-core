import pwdlib


class PwdlibPasswordService:
    def __init__(self) -> None:
        self._password_hasher = pwdlib.PasswordHash.recommended()

    def hash(self, plain_password: str) -> str:
        return self._password_hasher.hash(plain_password)

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return self._password_hasher.verify(
            password=plain_password,
            hash=password_hash,
        )
