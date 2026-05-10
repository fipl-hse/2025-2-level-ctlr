"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil
import sys

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    invalid seed url format
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    articles count out of range 1-100
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    invalid articles count type or value
    """


class IncorrectHeadersError(Exception):
    """
    headers must be a dictionary
    """


class IncorrectEncodingError(Exception):
    """
    encoding must be a string
    """


class IncorrectTimeoutError(Exception):
    """
    timeout must be positive integer less than 60
    """


class IncorrectVerifyError(Exception):
    """
    verify certificate and headless mode must be boolean
    """


class IncorrectVerifyCertificateError(Exception):
    """
    verify certificate must be boolean
    """


class ConfigValidationError(Exception):
    """
    configuration validation failed
    """


class ConfigLoadError(Exception):
    """
    cannot load configuration file
    """


class SeedUrlsError(Exception):
    """
    seed urls processing error
    """


class CustomTimeoutError(Exception):
    """
    request timeout
    """


class URLProcessingError(Exception):
    """
    url processing error
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
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            return ConfigDTO(**json.load(file))

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config_dto = self._extract_config_content()
        if not isinstance(config_dto.seed_urls, list):
            raise IncorrectSeedURLError()
        for seed_url in config_dto.seed_urls:
            if not isinstance(seed_url, str):
                raise IncorrectSeedURLError()
            if 'sufler.su' not in seed_url:
                raise IncorrectSeedURLError()
        if (not isinstance(config_dto.total_articles, int)
            or isinstance(config_dto.total_articles, bool)
            or config_dto.total_articles <= 0):
            raise IncorrectNumberOfArticlesError()
        if config_dto.total_articles > 100:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(config_dto.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(config_dto.encoding, str):
            raise IncorrectEncodingError()
        if (not isinstance(config_dto.timeout, int)
            or config_dto.timeout <= 0
            or config_dto.timeout > 60):
            raise IncorrectTimeoutError()
        if not isinstance(config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError()
        if not isinstance(config_dto.headless_mode, bool):
            raise IncorrectVerifyError()
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
        if not isinstance(href, str):
            return ''
        if href.startswith('/'):
            return f"https://sufler.su{href}"
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
            try:
                response = make_request(seed_url, self.config)
            except requests.exceptions.RequestException:
                continue
            if not response.ok:
                continue
            soup = BeautifulSoup(response.text, 'lxml')
            for link in soup.find_all('a', href=True):
                if len(self.urls) >= target_count:
                    return
                href = link.get('href')
                if (
                    not href
                    or not isinstance(href, str)
                    or href == '#'
                    or href.startswith('javascript')
                ):
                    continue
                if href.startswith('/'):
                    full_url = f"https://sufler.su{href}"
                elif 'sufler.su' in href:
                    full_url = href
                else:
                    continue
                if (
                    full_url == 'https://sufler.su/'
                    or '/feed' in full_url
                    or '/advanced_search' in full_url
                    or '/katalog' in full_url
                    or ('/wp-' in full_url
                    or '/category/' in full_url
                    or '/tag/' in full_url)
                    or '/author/' in full_url
                    ):
                    continue
                if full_url and full_url not in self.urls:
                    self.urls.append(full_url)

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


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
        super().__init__(config)
        self.visited_pages = []

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """
        target_count = self.config.get_num_articles()
        seed_urls = self.get_search_urls()
        exclude = ('/feed', '/advanced_search', '/katalog', '/wp-',
                '/category/', '/tag/', '/author/')
        for seed_url in seed_urls:
            if len(self.urls) >= target_count:
                break
            try:
                response = make_request(seed_url, self.config)
            except requests.exceptions.RequestException:
                continue
            if not response.ok:
                continue
            soup = BeautifulSoup(response.text, 'lxml')
            for link in soup.find_all('a', href=True):
                if len(self.urls) >= target_count:
                    return
                href = link.get('href')
                if (
                    not href
                    or not isinstance(href, str)
                    or href in ('#',)
                    or href.startswith('javascript')
                ):
                    continue
                if href.startswith('/'):
                    full_url = f"https://sufler.su{href}"
                elif 'sufler.su' in href:
                    full_url = href
                else:
                    continue
                if full_url == 'https://sufler.su/':
                    continue
                is_bad = any(p in full_url for p in exclude)
                if not is_bad and full_url not in self.urls:
                    self.urls.append(full_url)


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
        content_div = article_soup.find('div', class_='entry-content')
        if content_div:
            for tag in content_div.find_all(['script', 'style', 'aside', 'iframe']):
                tag.decompose()
            paragraphs = content_div.find_all('p')
            text_parts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            self.article.text = '\n\n'.join(text_parts)
        if not self.article.text:
            body = article_soup.find('body')
            if body:
                self.article.text = ' '.join(body.get_text().split())

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title = None
        meta_title = article_soup.find('meta', property='og:title')
        if meta_title and meta_title.get('content'):
            title = meta_title.get('content').strip()
        if not title:
            h1_entry = article_soup.find('h1', class_='entry-title')
            title = h1_entry.get_text(strip=True) if h1_entry else title
        if not title:
            h1 = article_soup.find('h1')
            title = h1.get_text(strip=True) if h1 else title
        if not title:
            title_tag = article_soup.find('title')
            title = title_tag.get_text(strip=True) if title_tag else title
        if not title:
            h2_entry = article_soup.find('h2', class_='entry-title')
            title = h2_entry.get_text(strip=True) if h2_entry else title
        if not title:
            h2 = article_soup.find('h2')
            title = h2.get_text(strip=True) if h2 else title
        if not title:
            post_title = article_soup.find(class_='post-title')
            title = post_title.get_text(strip=True) if post_title else title
        if title:
            self.article.title = title
        else:
            url_part = (self.full_url.split('/')[-2] if self.full_url.endswith('/')
                    else self.full_url.split('/')[-1])
            self.article.title = url_part if url_part else f"article_{self.article_id}"
        self.article.author = ['NOT FOUND']
        date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', article_soup.get_text())
        if date_match:
            day, month, year = map(int, date_match.groups())
            self.article.date = datetime.datetime(year, month, day)
        else:
            self.article.date = datetime.datetime.now()
        self.article.topics = []

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
        try:
            response = make_request(self.full_url, self.config)
            if not response.ok:
                return self.article
            soup = BeautifulSoup(response.text, 'lxml')
            self._fill_article_with_meta_information(soup)
            self._fill_article_with_text(soup)
            return self.article
        except requests.exceptions.RequestException:
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
    config_path = pathlib.Path("lab_5_scraper/scraper_config.json")
    if not config_path.exists():
        return
    config = Config(config_path)
    prepare_environment(ASSETS_PATH)
    crawler = CrawlerRecursive(config)
    crawler.find_articles()
    for i, url in enumerate(crawler.urls, 1):
        if i > config.get_num_articles():
            break
        parser = HTMLParser(full_url=url, article_id=i, config=config)
        article = parser.parse()
        if isinstance(article, Article):
            with open(article.get_raw_text_path(), "w", encoding="utf-8") as f:
                f.write(article.text)
            with open(article.get_meta_file_path(), "w", encoding="utf-8") as f:
                json.dump(article.get_meta(), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
