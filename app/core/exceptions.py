class LoginExpired(Exception):
    pass


class RiskControlDetected(Exception):
    pass


class CommentNotFound(Exception):
    pass


class OwnershipNotConfirmed(Exception):
    pass


class DeleteVerificationFailed(Exception):
    pass


class UnsupportedPageState(Exception):
    pass


class EdgeUnavailable(Exception):
    pass
