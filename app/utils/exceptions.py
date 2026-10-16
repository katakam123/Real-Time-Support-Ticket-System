from fastapi import HTTPException, status


def not_found(resource: str):
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


def forbidden(message: str = "Access denied"):
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=message,
    )


def conflict(message: str):
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=message,
    )


def bad_request(message: str):
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )