from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import service
from app.auth.deps import SESSION_COOKIE, CurrentUser, DbSession, require_roles, set_session_cookie
from app.auth.models import Role
from app.auth.schemas import LoginRequest, UserCreate, UserOut

router = APIRouter(prefix="/api")
admin_only = Depends(require_roles(Role.ADMINISTRATOR))


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: DbSession):
    user = service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password, or the account is temporarily locked",
        )
    set_session_cookie(response, user.id)
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.get("/users", response_model=list[UserOut], dependencies=[admin_only])
def list_users(db: DbSession):
    return service.list_users(db)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             dependencies=[admin_only])
def create_user(body: UserCreate, db: DbSession):
    try:
        return service.create_user(db, body.email, body.password, body.role)
    except service.EmailAlreadyUsed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already in use") from exc
