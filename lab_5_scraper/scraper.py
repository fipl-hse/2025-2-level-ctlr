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
    Raised when seed URL does not match standard pattern 'https?://(www.)?'
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Raised when total number of articles is out of range from 1 to 150
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Raised when total number of articles to parse is not integer or less than 0
    """

class IncorrectHeadersError(Exception):
    """
    Raised when headers are not in a form of dictionary
    """

class IncorrectEncodingError(Exception):
    """
    Raied when encoding is not specified as a string
    """

class IncorrectTimeoutError(Exception):
    """
    Raised when timeout value is not a positive integer that less than 60
    """

class IncorrectVerifyError(Exception):
    """
    Raised when verify certificate and headless mode values are not True or False
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
        config_dto = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = config_dto.seed_urls
        self._num_articles = config_dto.total_articles
        self._headers = config_dto.headers
        self._encoding = config_dto.encoding
        self._timeout = config_dto.timeout
        self._should_verify_certificate = config_dto.should_verify_certificate
        self._headless_mode = config_dto.headless_mode



    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        self._config_dto = self._extract_config_content()

        if not isinstance(self._config_dto.seed_urls, list):
            raise IncorrectSeedURLError('seed URL does not match standard pattern "https?://(www.)?"')

        url_pattern = re.compile(r"^https?://(www\.)?")
        for url in self._config_dto.seed_urls:
            if not isinstance(url, str) or not url_pattern.match(url):
                raise IncorrectSeedURLError('seed URL does not match standard pattern "https?://(www.)?"')

        if not isinstance(self._config_dto.total_articles, int):
            raise IncorrectNumberOfArticlesError('seed URL does not match standard pattern "https?://(www.)?"')
        if  self._config_dto.total_articles < 1:
            raise IncorrectNumberOfArticlesError("total number of articles is out of range from 1 to 150")
        if self._config_dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError("total number of articles is out of range from 1 to 150")

        if not isinstance(self._config_dto.headers, dict):
            raise IncorrectHeadersError("headers are not in a form of dictionary")

        if not isinstance(self._config_dto.encoding, str):
            raise IncorrectEncodingError("encoding must be specified as a string")

        if not isinstance(self._config_dto.timeout, int) or not 0 < self._config_dto.timeout < 60:
            raise IncorrectTimeoutError("timeout value must be a positive integer less than 60")

        if not isinstance(self._config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("verify certificate and headless mode values must either be True or False")

        if not isinstance(self._config_dto.headless_mode, bool):
            raise IncorrectVerifyError("verify certificate and headless mode values must either be True or False")



    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self._config_dto.seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self._config_dto.total_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self._config_dto.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self._config_dto.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self._config_dto.timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self._config_dto.should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self._config_dto.headless_mode


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
        url,
        headers = config.get_headers(),
        timeout = config.get_timeout(),
        verify = config.get_verify_certificate()
    )
    response.encoding = config.get_encoding()
    return response


class Crawler:
    """
    Crawler implementation.
    """

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
        self.url_pattern = re.compile(r'^https?://teatr-lib\.ru/Library/[\w\-/]+/?$')
        self._current_base = ""

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get('href')
        return urljoin(self._current_base, href) if href else ""


    def find_articles(self) -> None:
        """
        Find articles.
        """
        needed = self.config.get_num_articles()
        for seed in self.config.get_seed_urls():
            if len(self.urls) >= needed:
                break
            time.sleep(random.uniform(0.5, 3.0))
            try:
                response = make_request(seed, self.config)
            except Exception:
                    continue
            if response.status_code != 200:
                continue
            self._current_base = seed
            try:
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception:
                continue
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                url = self._extract_url(link)
                if url and self.url_pattern.match(url) and url not in self.urls:
                    self.urls.append(url)


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
        paragraphs = article_soup.find_all('p')
        if paragraphs:
            text = ' '.join(p.get_text(strip=True) for p in paragraphs)
        else:
            body = article_soup.find('body')
            text = body.get_text(separator=' ', strip=True) if body else ''
        self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1')
        self.article.title = title_tag.get_text(strip=True)
        date_tag = article_soup.find('time')
        if date_tag:
            date_str = date_tag.get('datetime') or date_tag.get_text(strip=True)
            self.article.date = self.unify_date_format(date_str)
        else:
            meta_date = article_soup.find('meta', {'name': 'date'})
            if meta_date and meta_date.get('content'):
                self.article.date = self.unify_date_format(meta_date['content'])
            else:
                self.article.date = datetime.datetime.now()


    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        return datetime.datetime.now()

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            if response.status_code != 200:
                return False
            soup = BeautifulSoup(response.text, 'lxml.parser')
            self._fill_article_with_text(soup)
            self._fill_article_with_meta_information(soup)
            return self.article
        except Exception:
            return False


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    path = pathlib.Path(base_path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)



def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    for idx, url in enumerate(crawler.urls[:configuration.get_num_articles()], start=1):
        parser = HTMLParser(full_url=url, article_id=idx, config=configuration)
        article = parser.parse()
        if article:
            to_raw(article)


if __name__ == "__main__":
    main()
