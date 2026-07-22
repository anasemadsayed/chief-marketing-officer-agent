"""
storage
=======

SQLite persistence layer.

- schema.py                                -> table creation (initialize_database_schema)
- database_connection.py                   -> connection/transaction management
- id_generator.py                          -> unique consulting case / record ids
- json_codec.py                            -> shared JSON (de)serialization helpers
- *_repository.py                          -> one repository per table, mapping
                                               domain models <-> rows

No SQL should be written or executed anywhere outside this package.
Every repository function takes/returns domain models from the `domain`
package — callers never see raw sqlite3.Row objects.
"""

from storage.business_diagnosis_repository import (
    get_business_diagnosis_by_case_id,
    save_business_diagnosis,
)
from storage.collected_source_repository import (
    create_and_save_collected_source,
    list_collected_sources_for_case,
    save_collected_source,
)
from storage.company_profile_repository import (
    get_company_profile_by_case_id,
    save_company_profile,
)
from storage.consulting_case_repository import (
    create_consulting_case,
    get_consulting_case_by_id,
    list_all_consulting_cases,
    update_consulting_case_status,
)
from storage.database_connection import get_database_connection, open_database_connection
from storage.extracted_company_information_repository import (
    get_extracted_information_by_case_id,
    save_extracted_information,
)
from storage.generated_report_repository import (
    get_generated_report_by_case_id,
    save_generated_report,
)
from storage.id_generator import generate_unique_consulting_case_id, generate_unique_record_id
from storage.market_research_repository import (
    get_market_research_by_case_id,
    save_market_research,
)
from storage.marketing_strategy_repository import (
    get_marketing_strategy_by_case_id,
    save_marketing_strategy,
)
from storage.schema import initialize_database_schema

__all__ = [
    "create_and_save_collected_source",
    "create_consulting_case",
    "generate_unique_consulting_case_id",
    "generate_unique_record_id",
    "get_business_diagnosis_by_case_id",
    "get_company_profile_by_case_id",
    "get_consulting_case_by_id",
    "get_database_connection",
    "get_extracted_information_by_case_id",
    "get_generated_report_by_case_id",
    "get_market_research_by_case_id",
    "get_marketing_strategy_by_case_id",
    "initialize_database_schema",
    "list_all_consulting_cases",
    "list_collected_sources_for_case",
    "open_database_connection",
    "save_business_diagnosis",
    "save_collected_source",
    "save_company_profile",
    "save_extracted_information",
    "save_generated_report",
    "save_market_research",
    "save_marketing_strategy",
    "update_consulting_case_status",
]
