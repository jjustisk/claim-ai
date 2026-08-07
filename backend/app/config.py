from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str = "changeme"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    azure_storage_connection_string: str = ""
    azure_storage_images_container_name: str = "claims-images"

    model_config = {"env_file": "../.env"}

settings = Settings()