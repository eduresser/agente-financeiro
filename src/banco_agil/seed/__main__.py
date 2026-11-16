from banco_agil.logging_utils import get_logger
from banco_agil.seed import bootstrap
from banco_agil.storage import default_data_dir

if __name__ == "__main__":
    data_dir = default_data_dir()
    created = bootstrap(data_dir)
    get_logger(__name__).warning("data ready at %s (created: %s)", data_dir, created or "none")
