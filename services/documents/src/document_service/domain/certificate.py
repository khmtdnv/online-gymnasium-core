from dataclasses import dataclass


class InvalidCertificateData(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CertificateData:
    student_full_name: str
    class_name: str
    academic_year: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.student_full_name.strip(),
                self.class_name.strip(),
                self.academic_year.strip(),
            )
        ):
            raise InvalidCertificateData
