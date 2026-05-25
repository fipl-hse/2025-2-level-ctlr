"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument

import datetime
import json
import pathlib
import re
import shutil

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """Raised when seed URL does not match standard pattern."""


class NumberOfArticlesOutOfRangeError(Exception):
    """Raised when total number of articles is out of range from 1 to 150."""


class IncorrectNumberOfArticlesError(Exception):
    """Raised when total number of articles is not integer or less than 0."""


class IncorrectHeadersError(Exception):
    """Raised when headers are not in a form of dictionary."""


class IncorrectEncodingError(Exception):
    """Raised when encoding is not specified as a string."""


class IncorrectTimeoutError(Exception):
    """Raised when timeout value is not a positive integer less than 60."""


class IncorrectVerifyError(Exception):
    """Raised when verify certificate value is not True or False."""


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
        self._extract_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, encoding='utf-8') as f:
            config_data = json.load(f)

        dto = ConfigDTO(
            seed_urls=config_data['seed_urls'],
            total_articles_to_find_and_parse=config_data['total_articles_to_find_and_parse'],
            headers=config_data['headers'],
            encoding=config_data['encoding'],
            timeout=config_data['timeout'],
            should_verify_certificate=config_data['should_verify_certificate'],
            headless_mode=config_data['headless_mode'],
        )

        self._seed_urls = dto.seed_urls
        self._num_articles = dto.total_articles
        self._headers = dto.headers
        self._encoding = dto.encoding
        self._timeout = dto.timeout
        self._should_verify_certificate = dto.should_verify_certificate
        self._headless_mode = dto.headless_mode

        return dto

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        with open(self.path_to_config, encoding='utf-8') as f:
            config_data = json.load(f)

        seed_urls = config_data.get('seed_urls')
        if not isinstance(seed_urls, list) or not seed_urls:
            raise IncorrectSeedURLError('seed_urls must be a non-empty list')
        for url in seed_urls:
            if not re.match(r'https?://(www\.)?', url):
                raise IncorrectSeedURLError(f'Invalid seed URL: {url}')

        total = config_data.get('total_articles_to_find_and_parse')
        if not isinstance(total, int) or isinstance(total, bool) or total < 1:
            raise IncorrectNumberOfArticlesError('total_articles must be a positive integer')
        if total > 150:
            raise NumberOfArticlesOutOfRangeError('total_articles must be between 1 and 150')

        headers = config_data.get('headers')
        if not isinstance(headers, dict):
            raise IncorrectHeadersError('headers must be a dictionary')

        encoding = config_data.get('encoding')
        if not isinstance(encoding, str):
            raise IncorrectEncodingError('encoding must be a string')

        timeout = config_data.get('timeout')
        if not isinstance(timeout, int) or isinstance(timeout, bool)\
        or timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError(
                'timeout must be a positive integer less than or equal to 60'
            )

        verify = config_data.get('should_verify_certificate')
        if not isinstance(verify, bool):
            raise IncorrectVerifyError('should_verify_certificate must be True or False')

        headless = config_data.get('headless_mode')
        if not isinstance(headless, bool):
            raise IncorrectVerifyError('headless_mode must be True or False')

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
        verify=config.get_verify_certificate(),
    )
    response.encoding = config.get_encoding()
    return response


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: re.Pattern | str = re.compile(r"https?://(www\.)?mnogo-smysla\.ru/")

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
        href = article_bs.get('href', '')
        if isinstance(href, str) and re.match(self.url_pattern, href):
            return href
        return ''


    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            try:
                response = make_request(seed_url, self.config)
                if response.status_code != 200:
                    continue
            except requests.RequestException:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)

            for link in links:
                if len(self.urls) >= self.config.get_num_articles():
                    return
                url = self._extract_url(link)
                if "https://mnogo-smysla.ru/category" in url:
                    continue
                if url and url not in self.urls and url not in self.get_search_urls():
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
        content = article_soup.find('div', class_='sf-entry-content')

        for tag in content.find_all(['script', 'style']):
            tag.decompose()
        blocks = content.find_all(['p', 'h2', 'h3', 'blockquote'])
        # print(blocks)
        text = '\n'.join(
            b.get_text(strip=True) for b in blocks if b.get_text(strip=True)
        )

        self.article.text = text

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1', class_='sf-entry-title')
        self.article.title = title_tag.get_text(strip=True) if title_tag else 'NOT FOUND'

        self.article.author = ['NOT FOUND']

        date_tag = article_soup.find('meta', property='article:published_time')
        if date_tag and date_tag.get('content'):
            try:
                self.article.date = self.unify_date_format(date_tag['content'])
            except ValueError:
                self.article.date = datetime.datetime.now()
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
        date_str = date_str[:19].replace('T', ' ')
        return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')

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
        except requests.RequestException:
            return False

        article_soup = BeautifulSoup(response.text, 'html.parser')
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
    base_path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config=configuration)
    crawler.find_articles()

    for i, url in enumerate(crawler.urls, start=1):
        parser = HTMLParser(full_url=url, article_id=i, config=configuration)
        article = parser.parse()

        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)
            print(f'[{i}] Сохранена: {article.title}')

if __name__ == '__main__':
    main()
