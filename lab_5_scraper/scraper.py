"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import random
import re
import shutil
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Exception raised when seed URL does not match the standard URL pattern.
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Exception raised when the total number of articles exceeds the allowed range.
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Exception raised when the total number of articles is not a positive integer.
    """

class IncorrectHeadersError(Exception):
    """
    Exception raised when headers are not provided as a dictionary.
    """

class IncorrectEncodingError(Exception):
    """
    Exception raised when encoding is not specified as a string.
    """

class IncorrectTimeoutError(Exception):
    """
    Exception raised when timeout is not a positive integer between 0 and 60.
    """

class IncorrectVerifyError(Exception):
    """
    Exception raised when verify_certificate or headless_mode is not a boolean value.
    """

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
        self._validate_config_content()
        dto = self._extract_config_content()
        self._seed_urls = dto.seed_urls
        self._num_articles = dto.total_articles
        self._headers = dto.headers
        self._encoding = dto.encoding
        self._timeout = dto.timeout
        self._should_verify_certificate = dto.should_verify_certificate

        self._headless_mode = dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return ConfigDTO(**raw)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        dto = self._extract_config_content()

        url_pattern = re.compile(r"https?://(www\.)?")
        if not isinstance(dto.seed_urls, list):
            raise IncorrectSeedURLError("seed_urls must be a list")
        for url in dto.seed_urls:
            if not isinstance(url, str) or not re.match(url_pattern, url):
                raise IncorrectSeedURLError(f"Incorrect seed URL: {url}")
        
        if (not isinstance(dto.total_articles, int) or dto.total_articles < 1):
            raise IncorrectNumberOfArticlesError(
                "Total number of articles must be a positive integer"
            )
        if dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError(
                "Total number of articles must not exceed 150"
            )

        if not isinstance(dto.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")

        if not isinstance(dto.encoding, str):
            raise IncorrectEncodingError("Encoding must be a string")

        if not isinstance(dto.timeout, int) or dto.timeout < 0 or dto.timeout > 60:
            raise IncorrectTimeoutError("Timeout must be an integer between 0 and 60")

        if not isinstance(dto.should_verify_certificate, bool) or \
           not isinstance(dto.headless_mode, bool):
            raise IncorrectVerifyError("should_verify_certificate and headless_mode must be boolean")

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
        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
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
    try:
        response = requests.get(
            url,
            headers=config.get_headers(),
            timeout=config.get_timeout(),
            verify=config.get_verify_certificate()
        )
        response.encoding = config.get_encoding()
        return response
    except (requests.exceptions.RequestException, requests.exceptions.HTTPError):
        return None


class Crawler:
    """
    Crawler implementation.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get("href", "")
        return urljoin("https://ru.wikisource.org", href)

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            response = make_request(seed_url, self.config)
            
            if not response or not response.ok:
                continue

            page_soup = BeautifulSoup(response.text, "lxml")
            
            for link_tag in page_soup.find_all("a", href=True):
                href = link_tag.get("href", "")
                
                if href.startswith("/wiki/") and ":" not in href.split("/wiki/")[1]:
                    full_url = self._extract_url(link_tag)
                    if full_url not in self.urls:
                        self.urls.append(full_url)

                if len(self.urls) >= self.config.get_num_articles():
                    return
            
            time.sleep(random.uniform(1, 2))

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


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
        self.full_url = full_url
        self.article_id = article_id
        self.config = config
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        main_content = article_soup.find("div", {"class": "mw-parser-output"})
        
        if main_content:
            for junk in main_content.find_all(["style", "script", "sup"]):
                junk.decompose()
            self.article.text = main_content.get_text(separator="\n", strip=True)
        else:
            self.article.text = ""

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
        response = make_request(self.full_url, self.config)

        if not response or response.status_code != 200:
            return False

        article_soup = BeautifulSoup(response.text, "lxml")
        self._fill_article_with_text(article_soup)
        self._fill_article_with_meta_information(article_soup)

        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    base_path = pathlib.Path(base_path)
    if base_path.exists():
        shutil.rmtree(base_path)
    base_path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    print(f"Articles found: {len(crawler.urls)}")
    for i, url in enumerate(crawler.urls, start=1):
        parser = HTMLParser(full_url=url, article_id=i, config=configuration)
        article = parser.parse()
        time.sleep(random.uniform(1, 3))
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)
            print(f"Article {i} saved: {url}")


if __name__ == "__main__":
    main()
