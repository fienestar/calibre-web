# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2021 OzzieIsaacs
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.

import dataclasses
import re
from concurrent import futures
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from html2text import HTML2Text
from lxml import etree

from cps.services.Metadata import Metadata, MetaRecord, MetaSourceInfo


def html2text(html: str) -> str:
    h2t = HTML2Text()
    h2t.body_width = 0
    h2t.single_line_break = True
    h2t.emphasis_mark = "*"
    return h2t.handle(html)

class Aladin(Metadata):
    __name__ = "Aladin"
    __id__ = "aladin"

    MAX_ITEMS = 10

    DESCRIPTION = "aladin.co.kr"
    META_URL = "https://www.aladin.co.kr/"
    BOOK_URL = "https://www.aladin.co.kr/shop/wproduct.aspx"
    SEARCH_URL = f"https://www.aladin.co.kr/search/wsearchresult.aspx?SearchTarget=All&ViewRowCount={MAX_ITEMS}&SearchWord="
    

    ITEM_XPATH = "//div[@class='ss_book_box']"
    AUTHORS_AND_PUBLISHER_XPATH = "//li[@class='Ere_sub2_title']"
    TITLE_XPATH = "//meta[@property='og:title']"
    COVER_XPATH = "//meta[@property='og:image']"
    DESCRIPTION_XPATH = "//meta[@property='og:description']"
    ISBN_XPATH = "//meta[@property='books:isbn']"
    PUBLISHED_DATE_XPATH = "//meta[@itemprop='datePublished']"
    RAITING10_XPATH = "//a[@class='Ere_sub_pink Ere_fs16 Ere_str']"

    AUTHOR_END_MARK = '(지은이)'

    def search(
        self, query: str, generic_cover: str = "", locale: str = "en"
    ) -> Optional[List[MetaRecord]]:
        val = list()    
        if self.active:
            query = self._parse_query(query)
            book_id_list = self._search_book_id(query)

            if not book_id_list:
                print('No book found')
                return None
            
            with futures.ThreadPoolExecutor(
                max_workers=5, thread_name_prefix='aladin'
            ) as executor:
                future_list = [
                    executor.submit(
                        self._fetch_book,
                        book_id,
                        generic_cover
                    )
                    for book_id in book_id_list
                ]

                val = [
                    future.result() for future in futures.as_completed(future_list)
                    if future.result()
                ]
        return val
    
    def _get_description(self, html: etree.ElementTree) -> str:
        # you can get long description from https://www.aladin.co.kr/shop/product/getContents.aspx?ISBN={isbn}&name=Introduce
        # but short description is enough
        return html.xpath(self.DESCRIPTION_XPATH)[0].get("content")

    def _parse_query(self, query: str) -> str:
            title_tokens = list(self.get_title_tokens(query, strip_joiners=False))
            if title_tokens:
                tokens = [quote(t.encode("utf-8")) for t in title_tokens]
                return "+".join(tokens)
            else:
                return query
            
    def _http_get(self, url: str) -> Optional[etree.ElementTree]:
        try:
            res = requests.get(url)
            res.raise_for_status()
            text = res.content.decode("utf8")
            return etree.HTML(text)
        except:
            return None
            
    def _search_book_id(self, query: str) -> Optional[List[str]]:
        html = self._http_get(Aladin.SEARCH_URL + query)

        if html == None:
            return None
        
        item_elements = html.xpath(self.ITEM_XPATH)[:10]

        return [
            element.attrib['itemid']
            for element in item_elements
            if 'itemid' in element.attrib
        ]

    def _fetch_book(
        self, id: str, generic_cover: str
    ) -> Optional[MetaRecord]:
        url = self.BOOK_URL + '?ItemId=' + id
        html = self._http_get(url)

        if html == None:
            return None
        
        try:
            title = html.xpath(self.TITLE_XPATH)[0].get("content")
            authors, publisher = self._parse_author_and_publisher(html)
            source = MetaSourceInfo(
                id=self.__id__,
                description=self.DESCRIPTION,
                link=self.META_URL,
            )
            cover = html.xpath(self.COVER_XPATH)[0].get("content") or generic_cover
            description = self._get_description(html)
            identifiers = {
                "isbn": html.xpath(self.ISBN_XPATH)[0].get("content")
            }
            publishedDate = html.xpath(self.PUBLISHED_DATE_XPATH)[0].get("content")
            try:
                raiting_10 = float(html.xpath(self.RAITING10_XPATH))[0].text.strip()
                raiting = int(raiting_10 // 2 + 0.5)
            except Exception:
                raiting = 0
            
            return MetaRecord(
                id=id,
                title=title,
                authors=authors,
                url=url,
                source=source,
                cover=cover,
                description=description,
                identifiers=identifiers,
                publisher=publisher,
                publishedDate=publishedDate,
                rating=raiting,
            )
        except Exception as e:
            return None
    
    def _parse_author_and_publisher(self, html) -> tuple[List[str], str]:
        sub = list(html.xpath(self.AUTHORS_AND_PUBLISHER_XPATH)[0].itertext())
        authors = []

        i = 0
        while i != len(sub):
            author = sub[i].strip()
            i += 1
            if self.AUTHOR_END_MARK in author:
                break
            if author != "," and author != "":
                authors.append(author)

        date_string = html.xpath(self.PUBLISHED_DATE_XPATH)[0].get("content").strip()
        while i != len(sub) and sub[i].strip() != date_string:
            i += 1

        #print(sub, date_string, i)

        if i != len(sub):
            publisher = sub[i - 1]
        else:
            publisher = ""

        return authors, publisher
