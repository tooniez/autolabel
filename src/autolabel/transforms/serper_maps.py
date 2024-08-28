from collections import defaultdict
import json
from autolabel.cache import BaseCache
from autolabel.transforms import BaseTransform
from langchain_community.utilities import GoogleSerperAPIWrapper
from typing import Dict, Any, List
import logging
import pandas as pd

from autolabel.transforms.schema import (
    TransformError,
    TransformErrorType,
    TransformType,
)

logger = logging.getLogger(__name__)


class RefuelSerperMapsWrapper(GoogleSerperAPIWrapper):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def arun(self, query: str, **kwargs: Any) -> Dict:
        """Run query through Serper.dev API and parse result async."""
        return self._process_response(await self.aresults(query))

    def _process_response(self, res: Dict) -> Dict:
        """
        Processes the response from Serper.dev API and returns the search results.
        """
        cleaned_res = {}
        if "error" in res.keys():
            raise ValueError(f"Got error from Serper.dev API: {res['error']}")
        if "places" in res.keys():
            cleaned_res["places"] = json.dumps(res["places"])
        return cleaned_res


class SerperMaps(BaseTransform):
    COLUMN_NAMES = ["places"]

    def __init__(
        self,
        cache: BaseCache,
        **kwargs: Any,
    ) -> None:
        super().__init__(cache, kwargs.pop("output_columns", {}))
        self.query_columns = kwargs.pop("query_columns", [])
        self.query_template = kwargs.pop("query_template", "")
        self.serper_args = kwargs
        self.serper_args["type"] = "places"
        self.serper_api_wrapper = RefuelSerperMapsWrapper(**self.serper_args)

    def name(self) -> str:
        return TransformType.WEB_SEARCH_SERPER

    async def _get_result(self, query):
        """
        Makes a request to Serper.dev API with the query
        and returns the search results.
        """
        try:
            search_result = await self.serper_api_wrapper.arun(query=query)
        except Exception as e:
            logger.error(f"Error while making request to Serper API: {str(e)}")
            raise TransformError(
                TransformErrorType.TRANSFORM_API_ERROR,
                f"Error while making request with query: {query}",
            )
        return search_result

    async def _apply(self, row: Dict[str, Any]) -> Dict[str, Any]:
        for col in self.query_columns:
            if col not in row:
                logger.warning(
                    f"Missing query column: {col} in row {row}",
                )
        query = self.query_template.format_map(
            defaultdict(str, {key: val for key, val in row.items() if val is not None})
        )
        search_result = self.NULL_TRANSFORM_TOKEN
        if pd.isna(query) or query == self.NULL_TRANSFORM_TOKEN:
            raise TransformError(
                TransformErrorType.INVALID_INPUT,
                f"Empty query in row {row}",
            )
        else:
            search_result = await self._get_result(query)
        transformed_row = {
            self.output_columns["places"]: search_result.get("places"),
        }

        return self._return_output_row(transformed_row)

    def params(self):
        return {
            "query_columns": self.query_columns,
            "query_template": self.query_template,
            "output_columns": self.output_columns,
            "params": self.serper_args,
        }

    def input_columns(self) -> List[str]:
        return self.query_columns