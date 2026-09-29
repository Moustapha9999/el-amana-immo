from fastapi import HTTPException, status


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        *,
        code: str | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, entity: str, entity_id: str | None = None):
        detail = f"{entity} introuvable"
        if entity_id:
            detail = f"{entity} {entity_id} introuvable"
        super().__init__(detail, status.HTTP_404_NOT_FOUND)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Accès refusé"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)


def raise_http_from_app(error: AppError) -> None:
    if error.code:
        raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message})
    raise HTTPException(status_code=error.status_code, detail=error.message)
