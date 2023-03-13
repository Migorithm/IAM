class UserAlreadyHasGroup(Exception):
    pass


class UserNotExistInGroup(Exception):
    pass


class ManagementPermissionRequired(Exception):
    pass


class AddUserToGroupRequestWithoutValidGroup(Exception):
    pass


class RemoveRequestedFromUserWithoutGroup(Exception):
    pass


class RoleNameTakenAlready(Exception):
    pass


class AccessPermissionRequired(Exception):
    pass


class InvalidOperation(Exception):
    pass
