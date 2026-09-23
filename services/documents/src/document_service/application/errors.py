class ApplicatinError(Exception):
    pass


class TemporaryStorageError(ApplicatinError):
    pass


class PermanentDocumentError(ApplicatinError):
    pass
