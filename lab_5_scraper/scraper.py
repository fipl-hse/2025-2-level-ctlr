"""
Crawler implementation.
Crawler implementation for royallib.com
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
    """Seed URL does not match standard pattern."""


class NumberOfArticlesOutOfRangeError(Exception):
    """Total number of articles is out of range from 1 to 150."""


class IncorrectNumberOfArticlesError(Exception):
    """Total number of articles to parse is not integer or less than 0."""


class IncorrectHeadersError(Exception):
    """Headers are not in a form of dictionary."""


class IncorrectEncodingError(Exception):
    """Encoding must be specified as a string."""


class IncorrectTimeoutError(Exception):
    """Timeout value must be a positive integer less than 60."""


class IncorrectVerifyError(Exception):
    """Verify certificate and headless mode values must either be True or False."""


class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path = CRAWLER_CONFIG_PATH) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        self.path_to_config = path_to_config
        self._config_dto = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self._config_dto.seed_urls
        self._num_articles = self._config_dto.total_articles
        self._headers = self._config_dto.headers
        self._encoding = self._config_dto.encoding
        self._timeout = self._config_dto.timeout
        self._should_verify_certificate = self._config_dto.should_verify_certificate
        self._headless_mode = self._config_dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return ConfigDTO(
            seed_urls=data.get('seed_urls', []),
            headers=data.get('headers', {}),
            total_articles_to_find_and_parse=data.get('total_articles_to_find_and_parse', 0),
            encoding=data.get('encoding', 'utf-8'),
            timeout=data.get('timeout', 30),
            should_verify_certificate=data.get('should_verify_certificate', True),
            headless_mode=data.get('headless_mode', False),
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        pattern = re.compile(r'^https?://(www\.)?')
        if not isinstance(self._config_dto.seed_urls, list):
            raise IncorrectSeedURLError('Seed URLs must be a list')
        for url in self._config_dto.seed_urls:
            if not isinstance(url, str) or not pattern.match(url):
                raise IncorrectSeedURLError(f'Invalid seed URL: {url}')

        total = self._config_dto.total_articles
        if not isinstance(total, int) or total <= 0:
            raise IncorrectNumberOfArticlesError('Total articles must be a positive integer')
        if total > 150:
            raise NumberOfArticlesOutOfRangeError('Total articles cannot exceed 150')

        if not isinstance(self._config_dto.headers, dict):
            raise IncorrectHeadersError('Headers must be a dictionary')

        if not isinstance(self._config_dto.encoding, str):
            raise IncorrectEncodingError('Encoding must be a string')

        timeout = self._config_dto.timeout
        if not isinstance(timeout, int) or timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError('Timeout must be an integer between 1 and 60')

        if not isinstance(self._config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError('should_verify_certificate must be a boolean')

        if not isinstance(self._config_dto.headless_mode, bool):
            raise IncorrectVerifyError('headless_mode must be a boolean')

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
    time.sleep(random.uniform(0.5, 1.5))
    response = requests.get(
        url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate()
    )
    response.encoding = config.get_encoding()
    response.raise_for_status()
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

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get('href')
        if not href or not isinstance(href, str):
            return ''
        full_url = urljoin('https://royallib.com', href)
        if re.search(r'/book/.*\.html', full_url):
            return full_url
        return ''

    def find_articles(self) -> None:
        """
        Find articles.
        """
        needed = self.config.get_num_articles()
        to_visit = list(self.config.get_seed_urls())
        visited = set()

        while len(self.urls) < needed and to_visit:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                response = make_request(current_url, self.config)
            except requests.exceptions.RequestException:
                continue

            soup = BeautifulSoup(response.text, 'lxml')

            for a in soup.find_all('a', href=True):
                if len(self.urls) >= needed:
                    break
                article_url = self._extract_url(a)
                if article_url and article_url not in self.urls:
                    self.urls.append(article_url)

            if len(self.urls) < needed:
                next_link = soup.find('a', rel='next')
                if next_link and next_link.get('href'):
                    href = next_link.get('href')
                    if isinstance(href, str):
                        next_url = urljoin(current_url, href)
                        if next_url not in visited:
                            to_visit.append(next_url)
        self.urls = self.urls[:needed]

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
        """
        text_div = article_soup.find('div', class_='text')
        if not text_div:
            text_div = article_soup.find('pre')
        if not text_div:
            text_div = article_soup.find('div', id='content')
        if not text_div:
            text_div = article_soup.find('body')

        if not text_div:
            self.article.text = ''
            return

        for unwanted in text_div(['script', 'style', 'a.button',
                                  'div.download','nav', 'header', 'footer', 'aside']):
            unwanted.decompose()

        paragraphs = text_div.find_all('p')
        if paragraphs:
            self.article.text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
        else:
            raw_text = text_div.get_text(strip=True)
            self.article.text = '\n\n'.join(line.strip() for line in raw_text.splitlines()
            if line.strip())

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.
        """
        title_tag = article_soup.find('h1')
        self.article.title = title_tag.get_text(strip=True) if title_tag else ''

        author_elem = article_soup.find('a', href=re.compile(r'/author/'))
        if author_elem:
            self.article.author = [author_elem.get_text(strip=True)]
        else:
            for elem in article_soup.find_all(string=re.compile(r'Автор:')):
                parent = elem.parent
                if parent:
                    author_text = parent.get_text().replace('Автор:', '').strip()
                    if author_text:
                        self.article.author = [author_text]
                        break
            else:
                self.article.author = ['NOT FOUND']

        date_str = ''
        for elem in article_soup.find_all(string=re.compile(r'Добавлена:')):
            date_str = elem.strip().replace('Добавлена:', '').strip()
            break
        if date_str:
            self.article.date = self.unify_date_format(date_str)
        else:
            self.article.date = datetime.datetime.now()

        topics = []
        for gl in article_soup.find_all('a', href=re.compile(r'/genre/')):
            topics.append(gl.get_text(strip=True))
        for kw in article_soup.find_all('a', href=re.compile(r'/keyword/')):
            topics.append(kw.get_text(strip=True))
        self.article.topics = topics

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        date_str = date_str.strip()
        months_ru = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        match = re.match(r'(\d{1,2})\s+([а-я]+)\s+(\d{4}),\s+(\d{1,2}):(\d{2})', date_str)
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            year = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            month = months_ru.get(month_name.lower(), 1)
            return datetime.datetime(year, month, day, hour, minute)
        try:
            return datetime.datetime.fromisoformat(date_str)
        except ValueError:
            return datetime.datetime.now()

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
        except requests.exceptions.RequestException:
            return False
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
    path = pathlib.Path(base_path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    config = Config()
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    for idx, url in enumerate(crawler.urls, start=1):
        if idx > config.get_num_articles():
            break
        parser = HTMLParser(url, idx, config)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)
    print(f"Done. Parsed {len(crawler.urls)} articles.")


if __name__ == "__main__":
    main()
