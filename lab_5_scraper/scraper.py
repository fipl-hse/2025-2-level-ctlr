"""
Crawler implementation.
"""


import datetime
import json
import pathlib
import re
import shutil
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH

sys.path.insert(0, str(Path(__file__).parent.parent))


class IncorrectSeedURLError(Exception):
    """
    Invalid seed URL format.
    """


class NumberOfArticlesOutOfRangeError(Exception):
    """
    Number of articles exceeds allowed range.
    """


class IncorrectNumberOfArticlesError(Exception):
    """
    Invalid number of articles.
    """


class IncorrectHeadersError(Exception):
    """
    Invalid headers.
    """


class IncorrectEncodingError(Exception):
    """
    Invalid encoding.
    """


class IncorrectTimeoutError(Exception):
    """
    Invalid timeout.
    """


class IncorrectVerifyError(Exception):
    """
    Invalid verify certificate or headless mode flag.
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
        with open(self.path_to_config, encoding="utf-8") as f:
            return ConfigDTO(**json.load(f))

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        dto = self._config

        if not isinstance(dto.seed_urls, list) or len(dto.seed_urls) == 0:
            raise IncorrectSeedURLError("seed_urls must be a non-empty list")

        for url in dto.seed_urls:
            if not isinstance(url, str) or not re.match(r"^https?://", url):
                raise IncorrectSeedURLError("Seed URL does not match pattern")

        if not isinstance(dto.total_articles, int) or dto.total_articles < 1:
            raise IncorrectNumberOfArticlesError("total_articles must be positive integer")

        if dto.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError("total_articles must be <= 150")

        if not isinstance(dto.headers, dict):
            raise IncorrectHeadersError("headers must be dict")

        if not isinstance(dto.encoding, str):
            raise IncorrectEncodingError("encoding must be str")

        if not isinstance(dto.timeout, int) or not (1 <= dto.timeout <= 60):
            raise IncorrectTimeoutError("timeout must be 1-60")

        if not isinstance(dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("should_verify_certificate must be bool")

        if not isinstance(dto.headless_mode, bool):
            raise IncorrectVerifyError("headless_mode must be bool")

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

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self.config = config
        self.urls: list[str] = []

    def _extract_url(self, article_bs: Tag) -> str:
        href = article_bs.get("href")
        if not href or not isinstance(href, str):
            return ""

        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = f"https://lib.ru{href}"
        else:
            full_url = f"https://lib.ru/PXESY/{href.lstrip('/')}"

        if not full_url.startswith("https://lib.ru/"):
            return ""

        return full_url

    def find_articles(self) -> None:
        target_count = self.config.get_num_articles()
        queue = self.config.get_seed_urls().copy()
        seen = set(queue)

        while queue and len(self.urls) < target_count:
            current_url = queue.pop(0)

            try:
                response = make_request(current_url, self.config)
                soup = BeautifulSoup(response.text, "html.parser")

                for link in soup.find_all("a", href=True):
                    found_url = self._extract_url(link)
                    if not found_url or found_url in seen:
                        continue

                    seen.add(found_url)

                    try:
                        article_response = make_request(found_url, self.config)
                        if article_response.status_code == 200 and found_url not in self.urls:
                            self.urls.append(found_url)
                    except Exception:
                        queue.append(found_url)

                    if len(self.urls) >= target_count:
                        break

            except Exception:
                continue

    def get_search_urls(self) -> list[str]:
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
        super().__init__(config)

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """
        # reuse parent method for now; can be replaced with recursive logic later if needed
        super().find_articles()


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
        pre = article_soup.find("pre")
        self.article.text = pre.get_text() if pre else article_soup.get_text()

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find("title")
        if title_tag:
            title = title_tag.get_text().strip()
            title = re.sub(r"\s*-\s*lib\.ru.*$", "", title, flags=re.I)
            self.article.title = title.strip()
        else:
            self.article.title = "No title"

        self.article.author = ["NOT FOUND"]
        self.article.topics = []

        self.article.date = self.unify_date_format("")

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
            resp = make_request(self.full_url, self.config)
            soup = BeautifulSoup(resp.text, "html.parser")
            self._fill_article_with_meta_information(soup)
            self._fill_article_with_text(soup)
            return self.article
        except Exception:
            return False


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles store
    """
    if isinstance(base_path, str):
        base_path = pathlib.Path(base_path)
    if base_path.exists():
        shutil.rmtree(base_path)
    base_path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    configuration = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)

    crawler = Crawler(configuration)
    crawler.find_articles()

    print(f"Found {len(crawler.urls)} articles. Starting parsing...")

    for i, url in enumerate(crawler.urls, start=1):
        print(f"[{i}/{len(crawler.urls)}] {url}")
        parser = HTMLParser(full_url=url, article_id=i, config=configuration)
        article = parser.parse()

        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)
            print(f"  ✓ Saved article {i}")
        else:
            print(f"  ✗ Failed to parse article {i}")

    print("\nScraping finished!")


if __name__ == "__main__":
    main()
