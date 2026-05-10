"""
Crawler implementation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO


class IncorrectEncodingError(Exception):
    pass

class IncorrectHeadersError(Exception):
    pass

class IncorrectNumberOfArticlesError(Exception):
    pass

class IncorrectSeedURLError(Exception):
    pass

class IncorrectTimeoutError(Exception):
    pass

class IncorrectVerifyCertificateError(Exception):
    pass

class IncorrectVerifyError(Exception):
    pass

class IncorrectHeadlessModeError(Exception):
    pass

class NumberOfArticlesOutOfRangeError(Exception):
    pass

class ConfigValidationError(Exception):
    pass

class ConfigLoadError(Exception):
    pass

class SeedUrlsError(Exception):
    pass

class TimeoutError(Exception):
    pass

class URLProcessingError(Exception):
    pass

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
        self._seed_urls = self.config_content.seed_urls
        self._validate_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        return ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            total_articles_to_find_and_parse=config_data.get('total_articles_to_find_and_parse', 100),
            headers=config_data.get('headers', {}),
            encoding=config_data.get('encoding', 'utf-8'),
            timeout=config_data.get('timeout', 10),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', False)
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        if not isinstance(self.config_content.seed_urls, list):
            raise ValueError()
        if not isinstance(self.config_content.total_articles, int) or self.config_content.total_articles <= 0:
            raise ValueError()
        if not isinstance(self.config_content.timeout, int) or self.config_content.timeout <= 0:
            raise ValueError()
        if not self.config_content.encoding:
            raise ValueError()

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self.config_content.seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self.config_content.total_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self.config_content.headers if self.config_content.headers else {}

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self.config_content.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self.config_content.timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self.config_content.should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self.config_content.headless_mode


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
        self.seed_urls = config.get_seed_urls()
        self.num_articles = config.get_num_articles()
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        link_tag = article_bs.find('a', href=True)
        if link_tag:
            href = link_tag.get('href')
            if href.startswith('/'):
                return f"https://sufler.su{href}"
            return href
        return ""

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.seed_urls:
            if len(self.urls) >= self.num_articles:
                break
            try:
                response = make_request(seed_url, self.config)
            except requests.exceptions.RequestException:
                continue
            try:
                soup = BeautifulSoup(response.text, 'lxml')
            except Exception:
                continue
            for link in soup.find_all('a', href=True):
                if len(self.urls) >= self.num_articles:
                    break
                href = link.get('href')
                if not href or href == '#' or href.startswith('javascript'):
                    continue
                if href.startswith('/'):
                    full_url = f"https://sufler.su{href}"
                elif 'sufler.su' in href:
                    full_url = href
                else:
                    continue
                if full_url == 'https://sufler.su/':
                    continue
                if '/feed' in full_url or '/advanced_search' in full_url or '/katalog' in full_url:
                    continue
                if '/wp-' in full_url or '/category/' in full_url or '/tag/' in full_url:
                    continue
                if '/author/' in full_url:
                    continue
                if full_url not in self.urls:
                    self.urls.append(full_url)

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.seed_urls

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
        self.visited_pages = []

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """
        for seed_url in self.seed_urls:
            if len(self.urls) >= self.num_articles:
                break
            current_url = seed_url
            while current_url and len(self.urls) < self.num_articles:
                if current_url in self.visited_pages:
                    break
                self.visited_pages.append(current_url)
                try:
                    response = make_request(current_url, self.config)
                except requests.exceptions.RequestException:
                    break
                try:
                    soup = BeautifulSoup(response.text, 'lxml')
                except Exception:
                    break
                for link in soup.find_all('a', href=True):
                    if len(self.urls) >= self.num_articles:
                        break
                    href = link.get('href')
                    if not href or href == '#' or href.startswith('javascript'):
                        continue
                    if href.startswith('/'):
                        full_url = f"https://sufler.su{href}"
                    elif 'sufler.su' in href:
                        full_url = href
                    else:
                        continue
                    if full_url == 'https://sufler.su/':
                        continue
                    if '/feed' in full_url or '/advanced_search' in full_url or '/katalog' in full_url:
                        continue
                    if '/wp-' in full_url or '/category/' in full_url or '/tag/' in full_url:
                        continue
                    if '/author/' in full_url or '/page/' in full_url:
                        continue
                    if full_url not in self.urls:
                        self.urls.append(full_url)
                current_url = None
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if href and href.startswith('/page/'):
                        if href.startswith('/'):
                            next_url = f"https://sufler.su{href}"
                        else:
                            next_url = href
                        if next_url not in self.visited_pages:
                            current_url = next_url
                            break


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
        content_div = article_soup.find('div', class_='entry-content')
        if content_div:
            for tag in content_div.find_all(['script', 'style', 'aside', 'iframe']):
                tag.decompose()
            paragraphs = content_div.find_all('p')
            text_parts = []
            for p in paragraphs:
                text = ' '.join(p.get_text().split())
                if text:
                    text_parts.append(text)
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
        title_tag = article_soup.find('h1')
        if not title_tag:
            title_tag = article_soup.find('h2', class_='entry-title')
        if not title_tag:
            title_tag = article_soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if title_text:
                self.article.title = title_text
            else:
                self.article.title = f"article_{self.article_id}"
        else:
            self.article.title = f"article_{self.article_id}"
        self.article.author = ["unknown author"]
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
        try:
            soup = BeautifulSoup(response.text, 'lxml')
        except Exception:
            return False
        self._fill_article_with_meta_information(soup)
        self._fill_article_with_text(soup)
        if not self.article.author:
            self.article.author = ["unknown author"]
        if self.article.date is None:
            self.article.date = datetime.datetime.now()
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
    config_path = pathlib.Path("lab_5_scraper/scraper_config.json")
    if not config_path.exists():
        return
    config = Config(config_path)
    if config.get_num_articles() <= 0:
        return
    crawler = CrawlerRecursive(config)
    crawler.find_articles()
    crawler.urls = [url for url in crawler.urls if url not in ['https://sufler.su', 'https://sufler.su/']]
    from core_utils.constants import ASSETS_PATH
    prepare_environment(ASSETS_PATH)
    articles_data = []
    total_to_parse = min(len(crawler.urls), config.get_num_articles())
    for i, url in enumerate(crawler.urls[:total_to_parse], 1):
        parser = HTMLParser(url, i, config)
        article = parser.parse()
        if article and article.text:
            with open(article.get_raw_text_path(), "w", encoding="utf-8") as f:
                f.write(article.text)
            with open(article.get_meta_file_path(), "w", encoding="utf-8") as f:
                json.dump(article.get_meta(), f, ensure_ascii=False, indent=2)
            articles_data.append(article.get_meta())
    log_path = ASSETS_PATH / "scraping_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_found": len(crawler.urls),
            "total_parsed": len(articles_data),
            "articles": articles_data
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
