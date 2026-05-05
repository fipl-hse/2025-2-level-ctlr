"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
from typing import List

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO


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
            num_articles=config_data.get('total_articles_to_find_and_parse', 100),
            headers=config_data.get('headers', {}),
            encoding=config_data.get('encoding', 'utf-8'),
            timeout=config_data.get('timeout', 10),
            verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', False)
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        if not isinstance(self.config_content.seed_urls, list):
            raise ValueError()
        if not isinstance(self.config_content.num_articles, int) or self.config_content.num_articles <= 0:
            raise ValueError()
        if self.config_content.num_articles > 1000:
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
        return self.config_content.num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        if self.config_content.headers:
            return {**default_headers, **self.config_content.headers}
        return default_headers

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
        return self.config_content.verify_certificate

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
    try:
        response = requests.get(
            url,
            headers=config.get_headers(),
            timeout=config.get_timeout(),
            verify=config.get_verify_certificate()
        )
        response.encoding = config.get_encoding()
        return response
    except requests.exceptions.RequestException:
        raise


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
        self.article_urls: List[str] = []

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
            if len(self.article_urls) >= self.num_articles:
                break  
            try:
                response = make_request(seed_url, self.config)
                soup = BeautifulSoup(response.text, 'lxml')
                article_links = soup.find_all('h2', class_='entry-title')
                for link in article_links:
                    if len(self.article_urls) >= self.num_articles:
                        break
                    url = self._extract_url(link)
                    if url and url not in self.article_urls:
                        self.article_urls.append(url)     
            except Exception as e:
                continue

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
        content_div = article_soup.find('div', class_='entry-content')
        if content_div:
            for unwanted in content_div.find_all(['script', 'style', 'aside', 'div', 'iframe']):
                unwanted.decompose()
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
        title = article_soup.find('h1', class_='entry-title')
        if title:
            self.article.title = title.get_text().strip()
        else:
            title = article_soup.find('title')
            if title:
                self.article.title = title.get_text().strip()
        date_tag = article_soup.find('time', class_='entry-date')
        if not date_tag:
            date_tag = article_soup.find('time')
        if date_tag and date_tag.get('datetime'):
            date_str = date_tag.get('datetime')
            self.article.date = self.unify_date_format(date_str)
        else:
            date_pattern = re.compile(r'\d{2,4}[-/]\d{1,2}[-/]\d{1,2}')
            text = article_soup.get_text()
            date_match = date_pattern.search(text)
            if date_match:
                self.article.date = self.unify_date_format(date_match.group())
        author_tag = article_soup.find('span', class_='author')
        if author_tag:
            author_name = author_tag.get_text().strip()
            if author_name:
                self.article.author = [author_name]

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
        # return datetime.datetime.now()

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            soup = BeautifulSoup(response.text, 'lxml')
            self._fill_article_with_meta_information(soup)
            self._fill_article_with_text(soup)
            return self.article
        except requests.exceptions.RequestException as e:
            return False


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    if base_path.exists():
        import shutil
        for i in base_path.iterdir():
            if i.is_file():
                i.unlink()
            elif i.is_dir():
                shutil.rmtree(i)
    else:
        base_path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """

if __name__ == "__main__":
    main()