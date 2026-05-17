"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Seed URL does not match standard pattern "https?://(www.)?
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    Total number of articles is out of range from 1 to 150.
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    Total number of articles to parse is not integer or less than 0.
    """


class IncorrectHeadersError(Exception):
    """
    Headers are not in a form of dictionary.
    """


class IncorrectEncodingError(Exception):
    """
    Encoding must be specified as a string.
    """


class IncorrectTimeoutError(Exception):
    """
    Timeout value must be a positive integer less than 60.
    """


class IncorrectVerifyError(Exception):
    """
    Verify certificate and headless mode values must either be ``True`` or ``False``.
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
        self.config_content = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self.config_content.seed_urls
        self._num_articles = self.config_content.total_articles
        self._headers = self.config_content.headers
        self._encoding = self.config_content.encoding
        self._timeout = self.config_content.timeout
        self._should_verify_certificate = self.config_content.should_verify_certificate
        self._headless_mode = self.config_content.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config) as file:
            config_data = json.load(file)
        configuration = ConfigDTO(**config_data)
        return configuration

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_content = self._extract_config_content()
        if not isinstance(config_content.seed_urls, list):
            raise IncorrectSeedURLError()
        for seed_url in config_content.seed_urls:
            if not re.match("https?://(www.)?", seed_url, 0):
                raise IncorrectSeedURLError()
        num_articles = config_content.total_articles
        if not isinstance(num_articles, int):
            raise IncorrectNumberOfArticlesError()
        if num_articles <= 0:
            raise IncorrectNumberOfArticlesError()
        if num_articles < 1 or num_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(config_content.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(config_content.encoding, str):
            raise IncorrectEncodingError()
        timeout = config_content.timeout
        if not (isinstance(timeout, int) and timeout < 60 and timeout >= 0):
            raise IncorrectTimeoutError()
        if not (isinstance(config_content.should_verify_certificate, bool) and isinstance(config_content.headless_mode, bool)):
            raise IncorrectVerifyError()

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
    headers = config.get_headers()
    timeout = config.get_timeout()
    verify = config.get_verify_certificate()
    try:
        response = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    except requests.exceptions.Timeout:
        print("Timeout: Server didn't respond in 3s")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
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
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        relative_link = article_bs.get("href")
        return relative_link

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.config.get_seed_urls():
            
            if len(self.urls) > self.config.get_num_articles():
                break
            
            response = make_request(seed_url, self.config)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text)
                all_links = soup.find_all("a") 
                for link_tag in all_links: #going through tags of links located in an html page
                    new_relative_url = self._extract_url(link_tag)
                    new_full_url = urljoin(seed_url, new_relative_url)
                    if (
                    #re.match("https://pravlitlug.ru/khudozhestvennaya-proza1/malaya-proza1/rasskazy1/item/", new_full_url)
                    #and
                    new_full_url not in self.urls
                    ):
                        self.urls.append(new_full_url)

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
        self.article = Article(full_url, article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        all_body = article_soup.find_all(["p", "blockquote"])
        texts = []
        for p in all_body:
            texts.append(p.text)
        self.article.text = " ".join(texts)

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
        try:
            response = requests.get(self.full_url)
            if response.status_code != 200:
                return False
            article_bs = BeautifulSoup(response.text)
            self._fill_article_with_text(article_bs)
        except:
            return False
        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    if base_path.exists():
        shutil.rmtree(base_path)
    base_path.mkdir(parents=True, exist_ok=True)



def main() -> None:
    """
    Entrypoint for scraper module.
    """


if __name__ == "__main__":
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    urls = crawler.urls

    for i, full_url in enumerate(urls, start=1):       
        parser = HTMLParser(full_url=full_url, article_id=i, config=configuration)
        article = parser.parse()
        to_raw(article)
