from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from app.config import settings

_blob_service_client: BlobServiceClient | None = None


async def get_blob_service_client() -> BlobServiceClient:
    """Return a shared BlobServiceClient for the configured storage account."""
    global _blob_service_client
    if _blob_service_client is None:
        if not settings.azure_storage_connection_string:
            raise RuntimeError(
                "AZURE_STORAGE_CONNECTION_STRING is not set. "
                "Add it to your .env file to use blob storage."
            )
        _blob_service_client = BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string
        )
    return _blob_service_client


async def close_blob_service_client() -> None:
    """Close the shared client. Call on application shutdown."""
    global _blob_service_client
    if _blob_service_client is not None:
        await _blob_service_client.close()
        _blob_service_client = None


async def get_container_client(container_name: str) -> ContainerClient:
    """Return a client for the named blob container."""
    client = await get_blob_service_client()
    return client.get_container_client(container_name)


async def get_images_container_client() -> ContainerClient:
    """Return a client for the claims-images blob container."""
    return await get_container_client(settings.azure_storage_images_container_name)


async def get_videos_container_client() -> ContainerClient:
    """Return a client for the claims-videos blob container."""
    return await get_container_client(settings.azure_storage_videos_container_name)


async def get_pds_policies_container_client() -> ContainerClient:
    """Return a client for the pds-policies blob container."""
    return await get_container_client(settings.azure_storage_pds_policies_container_name)


async def ensure_container_exists(container_name: str) -> ContainerClient:
    """Create the container if it does not already exist."""
    container = await get_container_client(container_name)
    if not await container.exists():
        await container.create_container()
    return container


async def upload_blob(
    blob_name: str,
    data: bytes,
    *,
    container_name: str,
    content_type: str | None = None,
    overwrite: bool = True,
) -> str:
    """Upload bytes to blob storage and return the blob URL."""
    container = await ensure_container_exists(container_name)
    blob_client = container.get_blob_client(blob_name)
    await blob_client.upload_blob(
        data,
        overwrite=overwrite,
        content_settings=ContentSettings(content_type=content_type)
        if content_type
        else None,
    )
    return blob_client.url


async def download_blob(blob_name: str, *, container_name: str) -> bytes:
    """Download a blob's contents."""
    container = await get_container_client(container_name)
    blob_client = container.get_blob_client(blob_name)
    stream = await blob_client.download_blob()
    return await stream.readall()


async def delete_blob(blob_name: str, *, container_name: str) -> None:
    """Delete a blob from storage."""
    container = await get_container_client(container_name)
    blob_client = container.get_blob_client(blob_name)
    await blob_client.delete_blob()


async def list_blobs(*, container_name: str, prefix: str = "") -> list[str]:
    """List blob names in a container, optionally filtered by prefix."""
    container = await get_container_client(container_name)
    names: list[str] = []
    async for blob in container.list_blobs(name_starts_with=prefix or None):
        names.append(blob.name)
    return names


async def upload_image(
    blob_name: str,
    data: bytes,
    *,
    content_type: str | None = None,
    overwrite: bool = True,
) -> str:
    """Upload an image to the claims-images container."""
    return await upload_blob(
        blob_name,
        data,
        container_name=settings.azure_storage_images_container_name,
        content_type=content_type,
        overwrite=overwrite,
    )


async def download_image(blob_name: str) -> bytes:
    """Download an image from the claims-images container."""
    return await download_blob(
        blob_name,
        container_name=settings.azure_storage_images_container_name,
    )


async def delete_image(blob_name: str) -> None:
    """Delete an image from the claims-images container."""
    await delete_blob(
        blob_name,
        container_name=settings.azure_storage_images_container_name,
    )


async def list_images(prefix: str = "") -> list[str]:
    """List image blob names in the claims-images container."""
    return await list_blobs(
        container_name=settings.azure_storage_images_container_name,
        prefix=prefix,
    )


async def upload_video(
    blob_name: str,
    data: bytes,
    *,
    content_type: str | None = None,
    overwrite: bool = True,
) -> str:
    """Upload a video to the claims-videos container."""
    return await upload_blob(
        blob_name,
        data,
        container_name=settings.azure_storage_videos_container_name,
        content_type=content_type,
        overwrite=overwrite,
    )


async def download_video(blob_name: str) -> bytes:
    """Download a video from the claims-videos container."""
    return await download_blob(
        blob_name,
        container_name=settings.azure_storage_videos_container_name,
    )


async def delete_video(blob_name: str) -> None:
    """Delete a video from the claims-videos container."""
    await delete_blob(
        blob_name,
        container_name=settings.azure_storage_videos_container_name,
    )


async def list_videos(prefix: str = "") -> list[str]:
    """List video blob names in the claims-videos container."""
    return await list_blobs(
        container_name=settings.azure_storage_videos_container_name,
        prefix=prefix,
    )


async def upload_pds_policy(
    blob_name: str,
    data: bytes,
    *,
    content_type: str | None = "application/pdf",
    overwrite: bool = True,
) -> str:
    """Upload a policy PDF to the pds-policies container."""
    return await upload_blob(
        blob_name,
        data,
        container_name=settings.azure_storage_pds_policies_container_name,
        content_type=content_type,
        overwrite=overwrite,
    )


async def download_pds_policy(blob_name: str) -> bytes:
    """Download a policy PDF from the pds-policies container."""
    return await download_blob(
        blob_name,
        container_name=settings.azure_storage_pds_policies_container_name,
    )


async def delete_pds_policy(blob_name: str) -> None:
    """Delete a policy PDF from the pds-policies container."""
    await delete_blob(
        blob_name,
        container_name=settings.azure_storage_pds_policies_container_name,
    )


async def list_pds_policies(prefix: str = "") -> list[str]:
    """List policy PDF blob names in the pds-policies container."""
    return await list_blobs(
        container_name=settings.azure_storage_pds_policies_container_name,
        prefix=prefix,
    )
