from authlib.flask.oauth2 import AuthorizationServer, ResourceProtector
from authlib.flask.oauth2.sqla import (
    create_query_client_func,
    create_save_token_func,
    create_revocation_endpoint,
    create_bearer_token_validator
)
from authlib.oauth2.rfc6749 import grants
from werkzeug.security import gen_salt
from .sql import *


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    def create_authorization_code(self, client, grant_user, request):
        code = gen_salt(48)
        item = OAuth2AuthorizationCode(
            code=code,
            client_id=client.client_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            user_id=grant_user.id
        )
        db.session.add(item)
        db.session.commit()
        return code

    def parse_authorization_code(self, code, client):
        item = OAuth2AuthorizationCode.query.filter_by(
            code=code, client_id=client.client_id).first()
        if item and not item.is_expired():
            return item

    def delete_authorization_code(self, authorization_code):
        db.session.delete(authorization_code)
        db.session.commit()

    def authenticate_user(self, authorization_code):
        return User.query.get(authorization_code.user_id)


class PasswordGrant(grants.ResourceOwnerPasswordCredentialsGrant):
    def authenticate_user(self, username, password):
        user = User.query.filter_by(username=username).first()
        if user is not None and user.check_password(password):
            return user


class RefreshTokenGrant(grants.RefreshTokenGrant):
    def authenticate_refresh_token(self, refresh_token):
        token = OAuth2Token.query.filter_by(refresh_token=refresh_token).first()
        if token and token.is_refresh_token_active():
            return token

    def authenticate_user(self, credential):
        return User.query.get(credential.user_id)

    def revoke_old_credential(self, credential):
        credential.revoked = True
        db.session.add(credential)
        db.session.commit()


query_client = create_query_client_func(db.session, OAuth2Client)
save_token = create_save_token_func(db.session, OAuth2Token)
authorization = AuthorizationServer(
    query_client=query_client,
    save_token=save_token,
)
require_oauth = ResourceProtector()


def config_oauth(app):
    # initialize database
    db.init_app(app)
    db.create_all(app=app)

    # initialize authorization server
    authorization.init_app(app)
    authorization.register_grant(grants.ImplicitGrant)
    authorization.register_grant(grants.ClientCredentialsGrant)
    authorization.register_grant(AuthorizationCodeGrant)
    authorization.register_grant(PasswordGrant)
    authorization.register_grant(RefreshTokenGrant)

    revocation_cls = create_revocation_endpoint(db.session, OAuth2Token)
    authorization.register_endpoint(revocation_cls)
    bearer_cls = create_bearer_token_validator(db.session, OAuth2Token)
    require_oauth.register_token_validator(bearer_cls())
