#!/usr/bin/env python3
"""Generate source and learner guides from reviewed project data, without audio."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_aistory as source

LABELS = {
    'verified_primary_abstract': '1차 자료 초록 확인, 전문 검토와 구분',
    'verified_institutional_search': '관련 기관 자료의 검색 결과 확인',
    'primary_author_retrospective_search': '저자 회고 자료의 검색 결과 확인',
    'primary_author_review_search': '저자 리뷰 자료의 검색 결과 확인',
    'verified_primary_release_search': '공식 발표의 검색 결과 확인',
    'verified_primary_metadata': '1차 자료 서지 정보 확인, 전문 미확인',
    'primary_author_review': '저자 리뷰 자료 확인',
    'verified_primary': '1차 자료 본문 확인',
    'verified_primary_search': '공식 자료 검색 결과 확인, 전문 확인 범위는 기록 참고',
    'verified_primary_release': '당사자의 공식 보도자료 확인',
    'verified_institutional': '관련 기관의 역사 설명 확인',
    'primary_publisher_metadata': '발행기관의 서지 정보 확인',
    'primary_metadata_only': '1차 자료의 서지 정보 확인, 전문 미확인',
    'primary_author_retrospective': '저자의 회고 자료 확인',
    'primary_fetch_blocked': '원문 접근 차단, 직접 확인하지 못함',
    'current_page_stale_or_conflicting': '공식 페이지와 다른 자료 사이 시점 충돌',
}

def outputs():
    records = json.loads((ROOT/'review/verified_sources.json').read_text(encoding='utf-8'))
    out = ['# AIStory 출처와 확인 범위', '',
           '확인 기준일: 2026-10-05. 논문·공식 발표·법원 문서와 관련 기관의 기록을 우선했습니다. '
           '모든 링크의 전문을 확인했다는 뜻은 아닙니다. 검색 결과·서지 정보·저자 회고·접근 차단을 구분해 적었습니다. '
           '당사자의 발표는 그 발표가 있었다는 근거이며 성능이나 안전성이 독립적으로 입증됐다는 뜻은 아닙니다.', '',
           '직함·기업가치·법률 절차는 기록에 표시한 시점의 내용입니다. 검색 결과로 확인한 자료와 서지 정보만 본 자료는 '
           '해당 범위 밖의 근거로 확대하지 않습니다. 원문에 없는 숫자·인과관계는 추가하지 않습니다.', '']
    for n,(_,title,_,_) in enumerate(source.CHAPTERS,1):
        out += [f'## {n}장 · {title}', '']
        for r in records:
            if r['chapter'] != n: continue
            out += [f"- [{r['title']}]({r['url']})",f"  - 자료의 날짜·관련 시점: {r['date']} · 확인일: {r['checked']} · 상태: {LABELS.get(r['verification'],r['verification'])}",
                    f"  - 확인한 주장: {r['claim']}"]
            if r.get('note'):out += [f"  - 범위와 주의점: {r['note']}"]
        out += ['']
    learning=['# AIStory 학습 안내','',
              '대상은 인공지능을 처음 체계적으로 배우려는 독자입니다. 미적분이나 프로그래밍 지식 없이 읽을 수 있도록 구성했습니다. '
              '연구자를 소개하지만 모든 인물과 연구 흐름을 빠짐없이 다룬 역사는 아닙니다.','',
              '## 학습 목표','',
              '1. 인물의 업적을 그 사람이 풀려던 문제와 연결해 설명합니다.',
              '2. 학습 방법·데이터·계산 자원·연구팀이 함께 만든 결과를 구분합니다.',
              '3. 회사의 목표와 검증된 결과, 기업가치와 기술 성능을 구분합니다.',
              '4. 새로운 주장에 대해 날짜·평가 조건·근거·남은 한계를 확인합니다.','',
              '## 읽는 순서','',
              '1부는 연구 주제별로 시간을 앞뒤로 이동합니다. 7장은 딥마인드의 활동을 먼저 훑고 8장은 2016년 바둑 대결로 돌아갑니다. '
              '9장은 1997년부터 언어 모델 구조를 살펴봅니다. 날짜를 기술 발전의 단일 직선으로 읽지 마세요.','',
              '각 장에서 대본을 읽은 뒤 답을 가리고 질문에 말로 답해 보세요. '
              '중요한 사람·방법·자료를 한 줄로 연결하고, 어디까지 검증된 성과인지 덧붙이면 좋습니다. '
              '음성은 아직 개정 원고로 렌더링하지 않았으므로 정해진 수업 시간이나 낭독 시간을 보장하지 않습니다.','']
    for n,(_,title,_,_) in enumerate(source.CHAPTERS,1):
        v=source.CHAPTER_VISUALS[n]
        learning += [f'## {n}장 · {title}','',f"질문: {v['learning_question']}",'',f"답의 핵심: {v['learning_answer']}",'']
    learning += ['## 종합 활동','',
                 '- 알렉스넷의 성과를 사람·학습 방법·데이터·하드웨어 네 가지로 나누어 설명해 보세요.',
                 '- 인물 한 명을 고르고 공동 저자와 선행 연구를 찾아 기여 관계를 그려 보세요.',
                 '- 기업의 새 모델 발표를 하나 읽고 목표·실험 결과·한계·발표일을 따로 적어 보세요.',
                 '- 회사 규모나 유명인의 평가만으로 모델의 정확성을 판단할 수 없는 이유를 설명해 보세요.','']
    return {'SOURCES.md':'\n'.join(out),'LEARNING_GUIDE.md':'\n'.join(learning)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    failed=[]
    for name,text in outputs().items():
        p=ROOT/name
        if args.check:
            if not p.is_file() or p.read_text(encoding='utf-8')!=text:failed.append(name)
        else:p.write_text(text,encoding='utf-8',newline='\n')
    if failed:raise SystemExit('Stale guides: '+', '.join(failed))
    print('Guides verified' if args.check else 'Source and learner guides generated')

if __name__=='__main__':main()
