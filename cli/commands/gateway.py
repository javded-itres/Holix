"""API Gateway command."""

from cli.utils.rich_console import print_info, print_success, print_error


def start_gateway(host: str, port: int, reload: bool):
    """Start the FastAPI gateway.

    Args:
        host: Host to bind
        port: Port to bind
        reload: Enable auto-reload
    """
    print_info(f"Starting Helix API Gateway on {host}:{port}")

    if reload:
        print_info("Auto-reload enabled")

    try:
        import uvicorn
        uvicorn.run(
            "api.gateway:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info"
        )
    except KeyboardInterrupt:
        print_info("\nShutting down gateway...")
    except Exception as e:
        print_error(f"Failed to start gateway: {e}")
