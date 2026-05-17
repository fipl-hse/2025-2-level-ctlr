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
from collections import deque


class IncorrectSeedURLError(Exception):
    """
    Seed URL does not match standard pattern "https?://(www.)
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    Total number of articles is out of range from 1 to 150
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    Total number of articles to parse is not integer or less than 0
    """


class IncorrectHeadersError(Exception):
    """
    Headers are not in a form of dictionary
    """


class IncorrectEncodingError(Exception):
    """
    Encoding must be specified as a string
    """


class IncorrectTimeoutError(Exception):
    """
    Timeout value must be a positive integer less than 60
    """


class IncorrectVerifyError(Exception):
    """
    Verify certificate value is not boolean
    """


class IncorrectHeadlessModeError(Exception):
    """
    Headless mode value is not boolean
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
        self._config = self._extract_config_content()
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
            config_data = json.load(file)
        return ConfigDTO(**config_data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        conf = self._config
        standard_pattern = re.compile(r"https?://(www\.)?")
        if not isinstance(conf.seed_urls, list):
            raise IncorrectSeedURLError()
        for url in conf.seed_urls: 
            if not isinstance(url, str) or not standard_pattern.match(url):
                raise IncorrectSeedURLError()
        if not isinstance(conf.total_articles, int):
            raise IncorrectNumberOfArticlesError()
        if conf.total_articles < 1:
            raise IncorrectNumberOfArticlesError()
        if conf.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(conf.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(conf.encoding, str):
            raise IncorrectEncodingError()
        if not isinstance(conf.timeout, int) or conf.timeout <= 0 or conf.timeout > 60:
            raise IncorrectTimeoutError()
        if not isinstance(conf.should_verify_certificate, bool):
            raise IncorrectVerifyError()
        if not isinstance(conf.headless_mode, bool):
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
        href = article_bs.get("href", "")
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return "https://old.mxat.ru/" + href.lstrip('/')


    def find_articles(self) -> None:
        """
        Find articles.
        """
        from collections import deque
        to_visit = deque(self.config.get_seed_urls())
        visited = set()
        while to_visit and len(self.urls) < self.config.get_num_articles():
            current_url = to_visit.popleft()
            if current_url in visited:
                continue
            visited.add(current_url)
            try:
                response = make_request(current_url, self.config)
                if not response.ok:
                    continue
                soup = BeautifulSoup(response.text, "lxml")
                for tag in soup.find_all("a", href=True):
                    href = tag.get("href", "")
                    if not href:
                        continue
                full_url = self._extract_url(tag)
                if not full_url or full_url in visited:
                    continue
                if not full_url.startswith("https://old.mxat.ru/"):
                    continue
                if full_url.endswith("/") and "/press/" in full_url:
                    if full_url not in visited:
                        to_visit.append(full_url)
                else:
                    is_valid_article = "/press/" in full_url
                    is_not_excluded = not any(word in full_url.lower() for word in ["search", "page", "award"])
                    if is_valid_article and is_not_excluded:
                        if full_url not in self.urls:
                            self.urls.append(full_url)
                            print(f"Found article {len(self.urls)}: {full_url}")
                        if len(self.urls) >= self.config.get_num_articles():
                            return
            except (requests.RequestException, AttributeError, ValueError):
                continue


    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


# 10
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
        texts = []
        content_block = article_soup.find("div", class_="content content_1")
        if content_block:
            for p in content_block.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    texts.append(text)
        self.article.text = "\n\n".join(texts) if texts else ""


    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        author_tag = article_soup.find("div", class_="author")
        if author_tag is None:
            self.article.author = ["NOT FOUND"]
        else:
            self.article.author = [author_tag.get_text(strip=True)]
        header_tag = article_soup.find("div", class_="thdr")
        if header_tag is not None:
            header_links = header_tag.find_all("a")
            if len(header_links) >= 2:
                self.article.title = header_links[1].get_text(strip=True)
                return
        title_tag = article_soup.find("title")
        if title_tag is None:
            self.article.title = "NOT FOUND"
        else:
            title_text = title_tag.get_text(strip=True)
            self.article.title = title_text.split(". Текст")[0]


    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        return datetime.datetime.strptime(date_str, "%d.%m.%y")

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
        if not response.ok:
            return False
        article_soup = BeautifulSoup(response.text, features="lxml")
        self._fill_article_with_text(article_soup)
        self._fill_article_with_meta_information(article_soup)
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
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()
    parsed_articles = 0
    for article_id, article_url in enumerate(crawler.urls, start=1):
        parser = HTMLParser(
            full_url=article_url,
            article_id=article_id,
            config=configuration,
        )
        article = parser.parse()
        if not article:
            continue
        to_raw(article)
        to_meta(article)
        parsed_articles += 1
    print(f"{parsed_articles} articles from the given URL are parsed.")


if __name__ == "__main__":
    main()
