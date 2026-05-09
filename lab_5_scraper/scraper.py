"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib

import re
from core_utils.article.errors import (
    IncorrectSeedURLError,
    NumberOfArticlesOutOfRangeError,
    IncorrectNumberOfArticlesError,
    IncorrectHeadersError,
    IncorrectEncodingError,
    IncorrectTimeoutError,
    IncorrectVerifyError,
)

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO


class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self.path_to_config = path_to_config
        self.config_dto: ConfigDTO = self._extract_config_content()
        self._validate_config_content()

        self._seed_urls: list[str] = self.config_dto.seed_urls
        self._num_articles: int = self.config_dto.total_articles
        self._headers: dict[str, str] = self.config_dto.headers
        self._encoding: str = self.config_dto.encoding
        self._timeout: int = self.config_dto.timeout
        self._verify_certificate: bool = self.config_dto.should_verify_certificate
        self._headless_mode: bool = self.config_dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, encoding="utf-8") as file:
            config_data = json.load(file)

        return ConfigDTO(
            seed_urls=config_data.get("seed_urls", []),
            total_articles_to_find_and_parse=config_data.get(
                "total_articles_to_find_and_parse", 10
            ),
            headers=config_data.get("headers", {}),
            encoding=config_data.get("encoding", "utf-8"),
            timeout=config_data.get("timeout", 10),
            should_verify_certificate=config_data.get("should_verify_certificate", True),
            headless_mode=config_data.get("headless_mode", False),
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        dto = self.config_dto

        if not isinstance(dto.seed_urls, list) or len(dto.seed_urls) == 0:
            raise IncorrectSeedURLError("seed_urls must be a non-empty list")

        for url in dto.seed_urls:
            if not isinstance(url, str) or not re.match(r"^https?://", url):
                raise IncorrectSeedURLError(
                    f"Seed URL does not match pattern 'https?://': {url}"
                )

        if not isinstance(dto.total_articles, int):
            raise IncorrectNumberOfArticlesError(
                "total_articles_to_find_and_parse must be integer"
            )

        if dto.total_articles < 1 or dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError(
                "total_articles_to_find_and_parse must be in range 1 to 150"
            )

        if not isinstance(dto.headers, dict):
            raise IncorrectHeadersError("headers must be a dictionary")

        if not isinstance(dto.encoding, str):
            raise IncorrectEncodingError("encoding must be a string")

        if not isinstance(dto.timeout, int) or dto.timeout < 1 or dto.timeout > 60:
            raise IncorrectTimeoutError("timeout must be integer 1 <= timeout <= 60")

        if not isinstance(dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("should_verify_certificate must be boolean")

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._headless_mode

def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """
    response = requests.get(
        url=url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate(),
    )

    response.encoding = config.get_encoding()

    response.raise_for_status()

    return response


class Crawler:
    """
    Crawler implementation.
    """
    url_pattern: re.Pattern | str = re.compile(r"https?://lib\.ru/PXESY/.+?\.txt$")

    #: Url pattern
    url_pattern: re.Pattern | str

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls: list[str] = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        if not isinstance(article_bs, Tag):
            return ""

        href = article_bs.get("href")
        if not href:
            return ""
        if href.startswith("/"):
            full_url = f"https://lib.ru{href}"
        elif not href.startswith("http"):
            full_url = f"https://lib.ru/PXESY/{href.lstrip('/')}"
        else:
            full_url = href

        if re.search(r"\.txt$", full_url):
            return full_url

        return ""

    def find_articles(self) -> None:
        """
        Find articles.
        """
        seed_urls = self.config.get_seed_urls()
        target_count = self.config.get_num_articles()

        for seed_url in seed_urls:
            if len(self.urls) >= target_count:
                break

            try:
                response = make_request(seed_url, self.config)
                main_bs = BeautifulSoup(response.text, "html.parser")

                for link_tag in main_bs.find_all("a", href=True):
                    article_url = self._extract_url(link_tag)

                    if article_url and article_url not in self.urls:
                        self.urls.append(article_url)

                    if len(self.urls) >= target_count:
                        break

            except Exception as e:
                print(f"Failed to process seed URL {seed_url}: {e}")
                continue

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


# 10


class CrawlerRecursive(Crawler):
    """
    Recursive implementation.

    Get one URL of the title page and find requested number of articles recursively.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the CrawlerRecursive class.

        Args:
            config (Config): Configuration
        """

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """


# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    if isinstance(base_path, str):
        base_path = pathlib.Path(base_path)

    if base_path.exists():
        import shutil
        shutil.rmtree(base_path)

    base_path.mkdir(parents=True, exist_ok=True)

def main() -> None:
    """
    Entrypoint for scraper module.
    """


if __name__ == "__main__":
    main()
