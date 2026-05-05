"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil
from random import randint
from time import sleep

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Exception raised when seed URL does not match standard pattern "https?://(www.)?".
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    Exception raised when total number of articles is out of range from 1 to 150.
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    Exception raised when total number of articles to parse is not integer or less than 0.
    """


class IncorrectHeadersError(Exception):
    """
    Exception raised when headers are not in a form of dictionary.
    """


class IncorrectEncodingError(Exception):
    """
    Exception raised when encoding must be specified as a string.
    """


class IncorrectTimeoutError(Exception):
    """
    Exception raised when timeout value must be a positive integer less than 60.
    """


class IncorrectVerifyError(Exception):
    """
    Exception raised when erify certificate and headless mode values must either be True or False.
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
        self._seed_urls = self._config.seed_urls
        self._num_articles = self._config.total_articles
        self._headers = self._config.headers
        self._encoding = self._config.encoding
        self._timeout = self._config.timeout
        self._should_verify_certificate = self._config.should_verify_certificate
        self._headless_mode = self._config.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise TypeError('Inapproprite type of config_file')
            return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_dto = self._extract_config_content()
        if not isinstance(config_dto.seed_urls, list):
            raise IncorrectSeedURLError('Seed URLs must be a list')
        pattern = r'^https?://(www\.)?'
        for url in config_dto.seed_urls:
            if not re.match(pattern, url):
                raise IncorrectSeedURLError('Seed URL does not match the standard pattern')
        if (
            not isinstance(config_dto.total_articles, int)
            or isinstance(config_dto.total_articles, bool)
            or config_dto.total_articles < 0
        ):
            raise (IncorrectNumberOfArticlesError('Number of articles is either not integer'
            'or less than 0'))
        if config_dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError('Number if articles is out of range')
        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError('Headers are not in a form of dictionary')
        if not isinstance(config_dto.encoding, str):
            raise IncorrectEncodingError('Encoding is not in a form of string')
        if (
            not isinstance(config_dto.timeout, int)
            or config_dto.timeout >= 60
            or config_dto.timeout < 0
        ):
            raise IncorrectTimeoutError('Timeout must be a positive integer and less than 60')
        if not isinstance(config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError('Verify certificate value must be boolean')
        if not isinstance(config_dto.headless_mode, bool):
            raise IncorrectVerifyError('Headless mode value must be boolean')
        self._config = config_dto

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
    response = requests.get(
        url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate()
    )
    response.encoding = config.get_encoding()
    sleep(randint(1, 3))
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
        link = article_bs.find('a', href=True)
        if not link:
            return ''
        href = link.get('href')
        if not isinstance(href, str) or '/theatre/blog/view/' not in href:
            return ''
        if href.startswith('/'):
            return 'https://www.ermolova.ru' + href
        return href

    def find_articles(self) -> None:
        """
        Find articles.
        """
        target_count = self.config.get_num_articles()
        seed_urls = self.get_search_urls()
        for seed_url in seed_urls:
            if len(self.urls) >= target_count:
                break
            response = make_request(seed_url, self.config)
            if not response.ok:
                continue
            soup = BeautifulSoup(response.text, 'lxml')
            for news_block in soup.find_all('div', class_='news-post'):
                if len(self.urls) >= target_count:
                    return
                url = self._extract_url(news_block)
                if url and url not in self.urls:
                    self.urls.append(url)

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


# 10


# class CrawlerRecursive(Crawler):
#     """
#     Recursive implementation.

#     Get one URL of the title page and find requested number of articles recursively.
#     """

#     def __init__(self, config: Config) -> None:
#         """
#         Initialize an instance of the CrawlerRecursive class.

#         Args:
#             config (Config): Configuration
#         """

#     def find_articles(self) -> None:
#         """
#         Find number of article urls requested.
#         """


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
        content_div = article_soup.find('div', class_='blog-content')
        if not content_div:
            return
        paragraphs = content_div.find_all('p')
        text = '\n'.join(p.get_text(strip=True) for p in paragraphs)
        self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h4', class_='head')
        if title_tag:
            self.article.title = title_tag.get_text(strip=True)
        date_tag = article_soup.find('p', class_='caption')
        if date_tag:
            data_text = date_tag.get_text(strip=True)
            self.article.date = self.unify_date_format(data_text)
        self.article.author = ['NOT FOUND']

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        day, month, year = map(int, date_str.split('.'))
        return datetime.datetime(year, month, day)

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        response = make_request(self.full_url, self.config)
        if not response.ok:
            return self.article
        soup = BeautifulSoup(response.text, 'lxml')
        self._fill_article_with_text(soup)
        self._fill_article_with_meta_information(soup)
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
    for i, fullurl in enumerate(crawler.urls):
        parser = HTMLParser(full_url=fullurl, article_id=i+1, config=configuration)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)
