# 584개 회귀 검사의 실제 범위

- 기준: fadda6ce33d19bf0d93ce409244b79af2fb56730, 2026-10-17 개선 전 테스트 소스 스냅샷.
- 테스트 파일 45개, `test_` 메서드 584개. 실제 주민 질문 584개나 정답률 100%를 뜻하지 않습니다.
- 함수 한 개에서 여러 문장·부정 조건·예외를 함께 검사하기도 합니다. DB·모델을 대역(Mock)으로 바꾼 검사가 포함됩니다.
- 검색/요청 의도, 공식 자료의 항목·대상·예외, 대화 문맥, 출처·연락처, 개인정보, 모델 응답 형식/시간 제한, 수집 Worker/캐시를 검사합니다.
- 아래 문장 목록은 테스트 함수에 직접 적힌 짧은 질문 형태 문자열을 정적으로 추출한 참고 자료입니다. 변수·공통 fixture·문장 조합은 빠질 수 있고 부정 검사에 쓰는 문자열도 포함됩니다. 실제 HTTP 질문 목록은 별도 문서를 보세요.

[실제 API 질문·판정·전체 답변 기록](C:/sahahaha/document/api_question_inventory_20261017.md)

현재 개선 후에는 **596개(기존584 + 신규12)**입니다. [이번 추가 문맥 검사12개](C:/sahahaha/tests/test_clarification_dialogue.py)와 [개선·실제 API 검증 보고서](C:/sahahaha/document/clarification_dialogue_report_20261017.md)를 함께 확인하세요. 아래584개 목록은 변경 전 기준으로 보존합니다.

## 어떤 것을 검사했나요?

| 구분 | 질문·검사 예 | 확인하는 내용 |
|---|---|---|
| 표현 변화 | 민증 발급, 주민 등록증 발급, 자전거 전용 도로 어떻게 돼? | 통칭·공백·어미가 바뀌어도 같은 업무를 찾는지 |
| 후속 대화 | 여권 준비물 → 성인이야 → 처음이야 | 연령·신규/재발급을 기억하고 다음 확인으로 연결하는지 |
| 대상·예외 | 부모의 미성년 여권 신청, 임산부 엽산 지원, 음식물쓰레기 제외 품목 | 다른 대상의 조건을 가져오거나 예외를 생략하지 않는지 |
| 항목 구분 | 신청방법/장소/비용/기간, 상담 수단/담당 전화 | 묻지 않은 항목이나 다른 사업으로 답하지 않는지 |
| 표·출처 | 침대 수수료, 여권 면수별 요금, 동별 시설 | 같은 행·열의 금액/대상/출처를 연결하는지 |
| 연락처 | 대표번호/직통/팩스, AI 업무 부서 | 확인된 공식 업무와 번호만 쓰는지 |
| 근거 부족 | 충돌하는 층수, 자료에 없는 약 복용량, 실시간 주차 칸 | 추측하지 않고 부족·충돌·조회 불가를 구분하는지 |
| 보호 | 개인정보, 화재 신고, 주식·코인 예측 | 개인정보 보호와 비행정/긴급 요청 처리가 맞는지 |
| 모델·운영 | 잘린 JSON, 범위 밖 출처 번호, 시간 초과, 캐시·수집 복구 | 오류가 있어도 허구 답변이나 서버 장애로 이어지지 않는지 |

이 표는 범위 설명입니다. 각 질문을 실제 모델이 답한 횟수나 정확도 표가 아닙니다.

## 파일별 검사 수

| 파일 | 검사 수 |
|---|---:|
| [test_accuracy_followup.py](C:/sahahaha/tests/test_accuracy_followup.py) | 16 |
| [test_accuracy_performance.py](C:/sahahaha/tests/test_accuracy_performance.py) | 4 |
| [test_accuracy_upgrade.py](C:/sahahaha/tests/test_accuracy_upgrade.py) | 10 |
| [test_accuracy_validation_repairs.py](C:/sahahaha/tests/test_accuracy_validation_repairs.py) | 7 |
| [test_answer_enrichment.py](C:/sahahaha/tests/test_answer_enrichment.py) | 14 |
| [test_answer_routing.py](C:/sahahaha/tests/test_answer_routing.py) | 14 |
| [test_candidate_search.py](C:/sahahaha/tests/test_candidate_search.py) | 8 |
| [test_colloquial_queries.py](C:/sahahaha/tests/test_colloquial_queries.py) | 16 |
| [test_concise_answers.py](C:/sahahaha/tests/test_concise_answers.py) | 35 |
| [test_conjunction_and_deadline_intent.py](C:/sahahaha/tests/test_conjunction_and_deadline_intent.py) | 5 |
| [test_contact_directory.py](C:/sahahaha/tests/test_contact_directory.py) | 19 |
| [test_contact_index.py](C:/sahahaha/tests/test_contact_index.py) | 7 |
| [test_evidence_decision.py](C:/sahahaha/tests/test_evidence_decision.py) | 10 |
| [test_explicit_source_fields.py](C:/sahahaha/tests/test_explicit_source_fields.py) | 4 |
| [test_free_route_priority.py](C:/sahahaha/tests/test_free_route_priority.py) | 7 |
| [test_gemma4_wording_repairs.py](C:/sahahaha/tests/test_gemma4_wording_repairs.py) | 8 |
| [test_general_answers.py](C:/sahahaha/tests/test_general_answers.py) | 24 |
| [test_generalization_repairs.py](C:/sahahaha/tests/test_generalization_repairs.py) | 34 |
| [test_grounded_planner.py](C:/sahahaha/tests/test_grounded_planner.py) | 14 |
| [test_institution_and_field_scope.py](C:/sahahaha/tests/test_institution_and_field_scope.py) | 8 |
| [test_llm_runtime.py](C:/sahahaha/tests/test_llm_runtime.py) | 10 |
| [test_local_inference.py](C:/sahahaha/tests/test_local_inference.py) | 5 |
| [test_merge_integration.py](C:/sahahaha/tests/test_merge_integration.py) | 11 |
| [test_metadata_provider.py](C:/sahahaha/tests/test_metadata_provider.py) | 5 |
| [test_official_content.py](C:/sahahaha/tests/test_official_content.py) | 40 |
| [test_official_faq.py](C:/sahahaha/tests/test_official_faq.py) | 18 |
| [test_online_location_and_day_fields.py](C:/sahahaha/tests/test_online_location_and_day_fields.py) | 5 |
| [test_passport_documents.py](C:/sahahaha/tests/test_passport_documents.py) | 11 |
| [test_payment_and_communication_intent.py](C:/sahahaha/tests/test_payment_and_communication_intent.py) | 5 |
| [test_priority_guard.py](C:/sahahaha/tests/test_priority_guard.py) | 3 |
| [test_query_field_routes.py](C:/sahahaha/tests/test_query_field_routes.py) | 12 |
| [test_question_intent.py](C:/sahahaha/tests/test_question_intent.py) | 14 |
| [test_recycling_category_rules.py](C:/sahahaha/tests/test_recycling_category_rules.py) | 5 |
| [test_reference_answers.py](C:/sahahaha/tests/test_reference_answers.py) | 19 |
| [test_reference_year_roles.py](C:/sahahaha/tests/test_reference_year_roles.py) | 4 |
| [test_request_metrics.py](C:/sahahaha/tests/test_request_metrics.py) | 2 |
| [test_requested_value_and_condition_scope.py](C:/sahahaha/tests/test_requested_value_and_condition_scope.py) | 5 |
| [test_response_performance.py](C:/sahahaha/tests/test_response_performance.py) | 10 |
| [test_reviewed_field_gate.py](C:/sahahaha/tests/test_reviewed_field_gate.py) | 7 |
| [test_safety_logic.py](C:/sahahaha/tests/test_safety_logic.py) | 50 |
| [test_semantic_ranker.py](C:/sahahaha/tests/test_semantic_ranker.py) | 32 |
| [test_source_requirement_groups.py](C:/sahahaha/tests/test_source_requirement_groups.py) | 12 |
| [test_specific_source_fields.py](C:/sahahaha/tests/test_specific_source_fields.py) | 7 |
| [test_vaccine_locations.py](C:/sahahaha/tests/test_vaccine_locations.py) | 17 |
| [test_worker_recovery.py](C:/sahahaha/tests/test_worker_recovery.py) | 11 |

## test_accuracy_followup.py (16개)

- [FollowupFieldTests.test_explicit_fields_win_over_incidental_application_actions](C:/sahahaha/tests/test_accuracy_followup.py:21)
  - 문장/변형: 여권 신분증은 원본 대신 휴대폰 사진이면 되나요?
  - 문장/변형: 주민등록증은 만 17세부터 맞나요?
  - 문장/변형: 인감증명서 대리로 떼려면 뭐가 필요해요?
  - 문장/변형: 소파 버리는 수수료 얼마예요?
  - 문장/변형: 냉장고 무료 방문수거 신청은 어디로 해요?
- [FollowupFieldTests.test_country_particle_is_not_photo_width](C:/sahahaha/tests/test_accuracy_followup.py:38)
- [FollowupFieldTests.test_proxy_permission_is_not_online_application_method](C:/sahahaha/tests/test_accuracy_followup.py:44)
- [FollowupFieldTests.test_residency_prerequisite_stays_with_supplement_schedule](C:/sahahaha/tests/test_accuracy_followup.py:58)
  - 문장/변형: 임산부 엽산제는 임신 몇 주까지 지원해요?
- [FollowupFieldTests.test_specific_unseen_food_cannot_be_answered_with_other_exclusions](C:/sahahaha/tests/test_accuracy_followup.py:65)
- [FollowupFieldTests.test_shell_wording_matches_the_actual_exclusion_without_inventing_food_rules](C:/sahahaha/tests/test_accuracy_followup.py:76)
- [FollowupFieldTests.test_old_rule_mentioned_to_ask_about_now_is_not_a_historical_request](C:/sahahaha/tests/test_accuracy_followup.py:84)
  - 문장/변형: 2024년 고향사랑기부 실적 통계를 알려줘
- [FollowupFieldTests.test_certificate_name_and_proxy_papers_match_their_own_heading](C:/sahahaha/tests/test_accuracy_followup.py:94)
  - 문장/변형: 동 주민센터에서 인감증명서를 대리로 떼려면 뭐가 필요해요?
- [FollowupFieldTests.test_polite_request_is_not_an_unknown_service_detail](C:/sahahaha/tests/test_accuracy_followup.py:104)
- [FollowupFieldTests.test_generic_issuing_counter_does_not_hide_certificate_papers](C:/sahahaha/tests/test_accuracy_followup.py:107)
  - 문장/변형: 동 주민센터에서 인감증명서를 대리로 떼려면 뭐가 필요해요?
- [FollowupFieldTests.test_procedure_deadline_keeps_owning_parent_and_extension](C:/sahahaha/tests/test_accuracy_followup.py:120)
  - 문장/변형: 정보공개청구를 내면 공개 여부 결정은 언제 알려주나요?
- [FollowupFieldTests.test_sofa_fee_requires_missing_size](C:/sahahaha/tests/test_accuracy_followup.py:133)
  - 문장/변형: 소파 버리는 수수료 얼마예요?
  - 문장/변형: 2인용 소파 수수료 얼마예요?
- [FollowupFieldTests.test_pregnancy_program_cannot_use_senior_flu_fields](C:/sahahaha/tests/test_accuracy_followup.py:137)
  - 문장/변형: 임신부 독감 예방접종 무료인가요?
- [FollowupFieldTests.test_gas_incident_is_immediate_but_billing_and_training_are_not](C:/sahahaha/tests/test_accuracy_followup.py:143)
  - 문장/변형: 집에서 가스 냄새가 심하게 나는데 민원을 넣으면 되나요?
  - 문장/변형: 가스가 새고 있어요 어디 신고해?
  - 문장/변형: 가스요금 지원 부서 알려줘
- [ContactRelationTests.test_ai_and_counselling_in_different_duties_do_not_establish_ai_counselling](C:/sahahaha/tests/test_accuracy_followup.py:159)
- [ContactRelationTests.test_fax_is_not_replaced_with_a_staff_phone](C:/sahahaha/tests/test_accuracy_followup.py:167)

## test_accuracy_performance.py (4개)

- [AccuracyPerformanceTests.test_changed_html_invalidates_reused_original_and_its_semantic_binding](C:/sahahaha/tests/test_accuracy_performance.py:12)
- [AccuracyPerformanceTests.test_unfiltered_vector_expansion_does_not_repeat_the_same_global_lookup](C:/sahahaha/tests/test_accuracy_performance.py:27)
- [AccuracyPerformanceTests.test_metadata_hints_still_expand_to_the_global_corpus](C:/sahahaha/tests/test_accuracy_performance.py:38)
- [AccuracyPerformanceTests.test_complete_method_in_its_own_subheading_can_skip_ambiguous_candidates](C:/sahahaha/tests/test_accuracy_performance.py:47)

## test_accuracy_upgrade.py (10개)

- [QueryConsistencyTests.test_renewal_variants_keep_the_complete_requirement_set](C:/sahahaha/tests/test_accuracy_upgrade.py:20)
  - 문장/변형: 성인 여권 재 발급 준비물 알려줘
- [QueryConsistencyTests.test_corrections_do_not_erase_negated_facts_or_change_age](C:/sahahaha/tests/test_accuracy_upgrade.py:32)
- [QueryConsistencyTests.test_clear_method_does_not_require_an_extra_question](C:/sahahaha/tests/test_accuracy_upgrade.py:42)
  - 문장/변형: 대형 폐기물 어떻게 버려요?
  - 문장/변형: 대형페기물 배출 방법 알려줘
- [QueryConsistencyTests.test_closed_typo_correction_and_spacing_preserve_service](C:/sahahaha/tests/test_accuracy_upgrade.py:49)
  - 문장/변형: 주민등룍증 발급 절차 알려줘
- [QueryConsistencyTests.test_count_limit_is_not_the_application_method_or_purchase_duration](C:/sahahaha/tests/test_accuracy_upgrade.py:54)
  - 문장/변형: 희망 도서 월별 신청 한도 알려줘
  - 문장/변형: 기부금 연간 한도 얼마
- [SourceOwnershipTests.test_general_institution_address_cannot_be_a_vaccination_venue](C:/sahahaha/tests/test_accuracy_upgrade.py:76)
- [SourceOwnershipTests.test_specific_benefit_retains_its_own_extra_child_condition](C:/sahahaha/tests/test_accuracy_upgrade.py:88)
  - 문장/변형: 둘째 아이만 있어도 광안대교 통행료가 무료인가요?
- [SourceOwnershipTests.test_compound_request_uses_actual_exclusions_not_a_lookup_instruction](C:/sahahaha/tests/test_accuracy_upgrade.py:104)
  - 문장/변형: 희망도서는 어디서 신청하고 어떤 책은 제외돼요?
- [SourceOwnershipTests.test_nested_exclusions_keep_the_label_and_do_not_absorb_other_cases](C:/sahahaha/tests/test_accuracy_upgrade.py:114)
- [SourceOwnershipTests.test_reply_duration_keeps_the_delay_exception](C:/sahahaha/tests/test_accuracy_upgrade.py:122)

## test_accuracy_validation_repairs.py (7개)

- [IndependentFailureTests.test_explicit_requested_items_keep_their_field](C:/sahahaha/tests/test_accuracy_validation_repairs.py:20)
  - 문장/변형: 금연클리닉에서 주는 약은 하루 몇 알 먹어야 하나요?
- [IndependentFailureTests.test_take_with_you_is_passport_documents_not_an_online_service](C:/sahahaha/tests/test_accuracy_validation_repairs.py:29)
- [IndependentFailureTests.test_online_result_cannot_be_replaced_with_the_first_clinical_visit](C:/sahahaha/tests/test_accuracy_validation_repairs.py:37)
  - 문장/변형: 보건증 검사는 이미 받았어요. 결과서 인터넷 발급은 어떻게 해요?
- [IndependentFailureTests.test_outdated_authentication_and_helpdesk_are_quarantined_without_erasing_the_route](C:/sahahaha/tests/test_accuracy_validation_repairs.py:48)
- [IndependentFailureTests.test_student_does_not_automatically_prove_a_youth_age_group](C:/sahahaha/tests/test_accuracy_validation_repairs.py:56)
  - 문장/변형: 청소년인가요
- [IndependentFailureTests.test_active_gas_verb_forms_are_immediate_but_negative_and_training_forms_are_not](C:/sahahaha/tests/test_accuracy_validation_repairs.py:62)
  - 문장/변형: 가스가 샜는데 어디로 연락해요?
  - 문장/변형: 가스가 새지 않는데 예방교육을 신청하고 싶어요
- [IndependentFailureTests.test_source_lookup_error_is_not_claimed_to_be_an_expired_page](C:/sahahaha/tests/test_accuracy_validation_repairs.py:68)
  - 문장/변형: 정화조 청소 주기 알려줘

## test_answer_enrichment.py (14개)

- [AnswerEnrichmentTests.test_target_answer_adds_real_service_and_venue_with_reservation_condition](C:/sahahaha/tests/test_answer_enrichment.py:39)
- [AnswerEnrichmentTests.test_model_and_source_fallback_both_enrich_without_additional_model_call](C:/sahahaha/tests/test_answer_enrichment.py:47)
- [AnswerEnrichmentTests.test_compound_question_gets_both_fields_and_keeps_visit_caution](C:/sahahaha/tests/test_answer_enrichment.py:63)
- [AnswerEnrichmentTests.test_missing_requested_location_is_stated_without_inventing_address](C:/sahahaha/tests/test_answer_enrichment.py:76)
- [AnswerEnrichmentTests.test_single_hours_question_does_not_expand_to_unrequested_location](C:/sahahaha/tests/test_answer_enrichment.py:81)
  - 문장/변형: 보건소 진료시간 알려줘
- [AnswerEnrichmentTests.test_service_question_adds_visit_information_from_same_program](C:/sahahaha/tests/test_answer_enrichment.py:85)
- [AnswerEnrichmentTests.test_repeated_targets_in_different_programs_are_not_joined](C:/sahahaha/tests/test_answer_enrichment.py:96)
- [AnswerEnrichmentTests.test_different_service_or_omitted_section_does_not_supply_extra_facts](C:/sahahaha/tests/test_answer_enrichment.py:101)
- [AnswerEnrichmentTests.test_length_limit_keeps_additional_fact_and_its_condition_together](C:/sahahaha/tests/test_answer_enrichment.py:107)
- [AnswerEnrichmentTests.test_conflicting_program_venues_are_not_added](C:/sahahaha/tests/test_answer_enrichment.py:115)
- [AnswerEnrichmentTests.test_explicit_mobile_program_uses_its_own_target_not_local_clinic_target](C:/sahahaha/tests/test_answer_enrichment.py:120)
- [AnswerEnrichmentTests.test_long_page_keeps_requested_program_visible_to_model](C:/sahahaha/tests/test_answer_enrichment.py:127)
- [AnswerEnrichmentTests.test_phone_notation_does_not_join_following_program_heading](C:/sahahaha/tests/test_answer_enrichment.py:141)
- [AnswerEnrichmentTests.test_heading_with_hours_starts_new_service_boundary](C:/sahahaha/tests/test_answer_enrichment.py:148)

## test_answer_routing.py (14개)

- [EmergencyRoutingTests.test_actual_reported_question_and_fire_variants](C:/sahahaha/tests/test_answer_routing.py:17)
  - 문장/변형: 당리동 인근 공장화제 어떻게신고해
  - 문장/변형: 공장 화제는 어디에 신고해야 돼?
  - 문장/변형: 공장에서 화제 났는데 어떻게 해?
  - 문장/변형: 당리동 인근 공장 화제 신고는 어떻게해?
  - 문장/변형: 공장 불났어 어디 신고해?
  - 문장/변형: 공장 화재 신고 담당부서 알려줘
- [EmergencyRoutingTests.test_news_and_fire_admin_queries_are_not_emergency_reporting](C:/sahahaha/tests/test_answer_routing.py:27)
  - 문장/변형: 화제가 된 행사는 어떻게 신고해?
  - 문장/변형: 소방 안전 교육 어디서 들어
  - 문장/변형: 화제가 된 사하구 행사 알려줘
  - 문장/변형: 화재 발생 건수는 어디서 봐?
- [EmergencyRoutingTests.test_fire_typo_normalization_has_context](C:/sahahaha/tests/test_answer_routing.py:31)
- [EmergencyRoutingTests.test_emergency_route_works_without_contact_file_models_or_database](C:/sahahaha/tests/test_answer_routing.py:36)
  - 문장/변형: 당리동 인근 공장 화제 신고는 어떻게해?
- [EmergencyRoutingTests.test_emergency_address_never_leaks_or_enters_history](C:/sahahaha/tests/test_answer_routing.py:44)
- [SubjectEvidenceTests.test_region_and_generic_report_word_cannot_pass_high_scores](C:/sahahaha/tests/test_answer_routing.py:57)
- [SubjectEvidenceTests.test_independent_docs_cannot_lend_each_other_missing_topics](C:/sahahaha/tests/test_answer_routing.py:64)
- [SubjectEvidenceTests.test_actual_topic_evidence_still_passes](C:/sahahaha/tests/test_answer_routing.py:68)
- [SubjectEvidenceTests.test_subject_keywords_remove_location_and_request_language](C:/sahahaha/tests/test_answer_routing.py:72)
  - 문장/변형: 당리동 인근 공장 화제 신고는 어떻게해?
  - 문장/변형: 여권 신규 발급 준비물 알려줘
- [SubjectEvidenceTests.test_wording_aliases_are_applied_before_morphology](C:/sahahaha/tests/test_answer_routing.py:76)
- [SubjectEvidenceTests.test_parking_report_selects_procedure_not_unrelated_enforcement_faq](C:/sahahaha/tests/test_answer_routing.py:80)
- [SubjectEvidenceTests.test_unusable_leading_source_does_not_hide_valid_next_source](C:/sahahaha/tests/test_answer_routing.py:88)
- [SubjectEvidenceTests.test_original_and_quoted_body_must_match_not_just_metadata_title](C:/sahahaha/tests/test_answer_routing.py:105)
- [SubjectEvidenceTests.test_generic_bm25_result_cannot_trigger_fast_path](C:/sahahaha/tests/test_answer_routing.py:116)
  - 문장/변형: 당리동 공장 소음 신고 어떻게해?

## test_candidate_search.py (8개)

- [CandidateSearchTests.test_multiple_chunks_cannot_outvote_other_sources](C:/sahahaha/tests/test_candidate_search.py:16)
- [CandidateSearchTests.test_raw_vector_similarity_is_not_replaced_by_rank_score](C:/sahahaha/tests/test_candidate_search.py:24)
- [CandidateSearchTests.test_original_is_kept_when_vector_chunk_shares_url](C:/sahahaha/tests/test_candidate_search.py:30)
- [CandidateSearchTests.test_keyword_hits_without_requested_facts_trigger_vector_search](C:/sahahaha/tests/test_candidate_search.py:37)
  - 문장/변형: 대형폐기물 수수료 얼마인가요?
- [CandidateSearchTests.test_conflicting_complete_sources_do_not_skip_semantics](C:/sahahaha/tests/test_candidate_search.py:48)
- [CandidateSearchTests.test_vector_failure_retains_lexical_candidates_with_failure_reason](C:/sahahaha/tests/test_candidate_search.py:53)
- [CandidateSearchTests.test_institution_hours_are_not_pregnancy_program_hours](C:/sahahaha/tests/test_candidate_search.py:63)
  - 문장/변형: 사하구 보건소 몇 시부터 진료해요?
- [CandidateSearchTests.test_other_district_cannot_borrow_saha_hours](C:/sahahaha/tests/test_candidate_search.py:67)

## test_colloquial_queries.py (16개)

- [ColloquialQueryTests.test_state_tail_preserves_bare_question_intent](C:/sahahaha/tests/test_colloquial_queries.py:22)
  - 문장/변형:  어떻게 돼?
  - 문장/변형:  어떻게 되나요?
  - 문장/변형:  어떻게돼요?
  - 문장/변형:  어떻게 됩니까?
- [ColloquialQueryTests.test_state_tail_keeps_explicit_action_and_compound_fields](C:/sahahaha/tests/test_colloquial_queries.py:29)
  - 문장/변형: 주민등록증 발급 절차는 어떻게 돼?
  - 문장/변형: 보건소 진료시간과 위치는 어떻게 되나요?
  - 문장/변형: 소방교육 어떻게 받아?
  - 문장/변형: 화재 어떻게 신고해?
  - 문장/변형: 자전거도로 이용비용은 어떻게 돼?
- [ColloquialQueryTests.test_abbreviation_keeps_issuance_subject_after_morphology](C:/sahahaha/tests/test_colloquial_queries.py:36)
  - 문장/변형: 민증 발급 절차 알려줘
  - 문장/변형: 민증발급 절차 알려줘
  - 문장/변형: 주민등록증 발급 절차 알려줘
- [ColloquialQueryTests.test_identity_lifecycle_one_question_and_short_followup](C:/sahahaha/tests/test_colloquial_queries.py:42)
  - 문장/변형: 민증 발급 절차 알려줘
  - 문장/변형: 여권 준비물 알려줘
- [ColloquialQueryTests.test_elided_map_followup_keeps_topic_without_changing_a_new_topic](C:/sahahaha/tests/test_colloquial_queries.py:52)
  - 문장/변형: 현황 지도 보고 싶어
  - 문장/변형: 비상급수시설 현황 지도 보고 싶어
  - 문장/변형: 주차장 지도 보고 싶어
  - 문장/변형: 소방교육 신청 방법 알려줘
  - 문장/변형: 자전거 전용 도로 어떻게 돼?
- [ColloquialQueryTests.test_health_certificate_method_does_not_assume_existing_test](C:/sahahaha/tests/test_colloquial_queries.py:63)
  - 문장/변형: 보건증 어떻게 받아?
  - 문장/변형: 보건증 수수료 알려줘
- [ColloquialQueryTests.test_fire_subject_cannot_be_replaced_even_with_high_semantic_score](C:/sahahaha/tests/test_colloquial_queries.py:75)
  - 문장/변형: 소방교육 어떻게 받아?
- [ColloquialQueryTests.test_identity_source_is_not_passport_or_other_lifecycle](C:/sahahaha/tests/test_colloquial_queries.py:85)
- [ColloquialQueryTests.test_additional_pages_are_refresh_targets_without_answer_text](C:/sahahaha/tests/test_colloquial_queries.py:93)
- [ColloquialQueryTests.test_submission_procedure_keeps_documents_deadline_and_exception](C:/sahahaha/tests/test_colloquial_queries.py:103)
  - 문장/변형: 전입신고 절차 어떻게 돼?
- [ColloquialQueryTests.test_actual_map_rule_is_left_for_factual_source_reader](C:/sahahaha/tests/test_colloquial_queries.py:113)
  - 문장/변형: 자전거도로 통행 규칙 알려줘
- [ColloquialQueryTests.test_dedicated_safety_facility_does_not_become_other_services](C:/sahahaha/tests/test_colloquial_queries.py:118)
  - 문장/변형: 소방교육 어떻게 받아?
- [ColloquialQueryTests.test_bicycle_map_same_navigation_without_fabricated_designation](C:/sahahaha/tests/test_colloquial_queries.py:127)
  - 문장/변형: 자전거 전용 도로 어떻게 돼?
  - 문장/변형: 자전거도로 어떻게 되나요?
  - 문장/변형: 자전거 전용도로 통행 규칙 알려줘
  - 문장/변형: 총 길이 몇 km야?
- [ColloquialQueryTests.test_road_topic_is_not_replaced_by_bicycle_accident_insurance](C:/sahahaha/tests/test_colloquial_queries.py:142)
  - 문장/변형: 자전거 전용도로 통행 규칙 알려줘
  - 문장/변형: 자전거 전용도로 어떻게 돼?
  - 문장/변형: 현황 지도 보고 싶어
- [ColloquialQueryTests.test_course_scope_cannot_be_assumed_from_an_application_question](C:/sahahaha/tests/test_colloquial_queries.py:152)
  - 문장/변형: 소방교육 어떻게 받아?
  - 문장/변형: 소방 안전교육 신청 방법 알려줘
  - 문장/변형: 소방교육 받고 싶어요
  - 문장/변형: 일반 주민 소방교육 어떻게 받아?
- [ColloquialQueryTests.test_detail_form_retains_field_pairs_and_discards_misleading_caption](C:/sahahaha/tests/test_colloquial_queries.py:169)
  - 문장/변형: 주민등록증 처음 발급 절차 알려줘

## test_concise_answers.py (35개)

- [ConciseAnswerTests.test_reported_recycling_sentence_keeps_wrapped_ending](C:/sahahaha/tests/test_concise_answers.py:25)
- [ConciseAnswerTests.test_incomplete_source_does_not_get_a_fabricated_ending](C:/sahahaha/tests/test_concise_answers.py:34)
- [ConciseAnswerTests.test_wrapped_exception_is_kept_whole](C:/sahahaha/tests/test_concise_answers.py:40)
- [ConciseAnswerTests.test_cut_exception_requires_clarification](C:/sahahaha/tests/test_concise_answers.py:45)
- [ConciseAnswerTests.test_exception_is_not_selected_without_the_rule_it_qualifies](C:/sahahaha/tests/test_concise_answers.py:49)
- [ConciseAnswerTests.test_condition_is_not_detached_from_its_conclusion](C:/sahahaha/tests/test_concise_answers.py:56)
- [ConciseAnswerTests.test_omitted_passage_edge_does_not_become_an_answer](C:/sahahaha/tests/test_concise_answers.py:60)
- [ConciseAnswerTests.test_wrapped_parentheses_are_balanced](C:/sahahaha/tests/test_concise_answers.py:65)
- [ConciseAnswerTests.test_table_header_is_not_joined_to_an_unfinished_claim](C:/sahahaha/tests/test_concise_answers.py:70)
- [ConciseAnswerTests.test_long_complete_sentence_is_not_sliced](C:/sahahaha/tests/test_concise_answers.py:74)
- [ConciseAnswerTests.test_passport_summary_preserves_photo_conditions](C:/sahahaha/tests/test_concise_answers.py:79)
- [ConciseAnswerTests.test_brief_must_keep_adjacent_exception](C:/sahahaha/tests/test_concise_answers.py:88)
- [ConciseAnswerTests.test_table_cells_are_not_reassigned_to_a_summary](C:/sahahaha/tests/test_concise_answers.py:94)
- [ConciseAnswerTests.test_too_large_exception_requires_narrowing](C:/sahahaha/tests/test_concise_answers.py:100)
- [ConciseAnswerTests.test_renewal_summary_keeps_existing_passport_requirement](C:/sahahaha/tests/test_concise_answers.py:105)
- [ConciseAnswerTests.test_cost_table_keeps_total_and_included_parts](C:/sahahaha/tests/test_concise_answers.py:111)
- [ConciseAnswerTests.test_passport_fee_uses_requested_faces](C:/sahahaha/tests/test_concise_answers.py:118)
- [ConciseAnswerTests.test_short_method_label_keeps_visit_requirement](C:/sahahaha/tests/test_concise_answers.py:123)
- [ClarificationFlowTests.test_broad_topics_prompt_one_focused_question](C:/sahahaha/tests/test_concise_answers.py:138)
  - 문장/변형: 복지 지원 알려줘
  - 문장/변형: 여권 알려줘
  - 문장/변형: 여권 준비물 알려줘
  - 문장/변형: 대형폐기물 수수료 알려줘
  - 문장/변형: 무인민원발급기 알려줘
- [ClarificationFlowTests.test_precise_question_is_answered_without_more_questions](C:/sahahaha/tests/test_concise_answers.py:146)
  - 문장/변형: 성인 신규 여권 준비물 알려줘
- [ClarificationFlowTests.test_typing_short_choices_keeps_question_context](C:/sahahaha/tests/test_concise_answers.py:150)
  - 문장/변형: 여권 준비물 알려줘
- [ClarificationFlowTests.test_choice_button_is_complete_question_and_new_topic_is_not_attached](C:/sahahaha/tests/test_concise_answers.py:167)
  - 문장/변형: 여권 준비물 알려줘
  - 문장/변형: 보건증 수수료 얼마야?
- [ClarificationFlowTests.test_reset_removes_pending_question](C:/sahahaha/tests/test_concise_answers.py:174)
  - 문장/변형: 여권 준비물 알려줘
- [ClarificationFlowTests.test_sessions_do_not_share_pending_question](C:/sahahaha/tests/test_concise_answers.py:181)
  - 문장/변형: 여권 준비물 알려줘
- [ClarificationFlowTests.test_after_clarification_followup_does_not_lose_resolved_topic](C:/sahahaha/tests/test_concise_answers.py:187)
- [ClarificationFlowTests.test_conversational_qualifiers_select_verified_passport_guide](C:/sahahaha/tests/test_concise_answers.py:196)
  - 문장/변형: 여권 준비물 알려줘 성인이야 처음이야
  - 문장/변형: 유료 성인예방접종 알려줘
- [ModelCompletionTests.test_token_limit_rejects_even_a_complete_visible_sentence](C:/sahahaha/tests/test_concise_answers.py:203)
- [ModelCompletionTests.test_incomplete_tail_and_unclosed_emphasis_are_rejected](C:/sahahaha/tests/test_concise_answers.py:207)
- [ModelCompletionTests.test_complete_short_bullets_and_decimals_are_accepted](C:/sahahaha/tests/test_concise_answers.py:211)
- [ModelCompletionTests.test_complete_but_long_answer_is_not_exposed](C:/sahahaha/tests/test_concise_answers.py:215)
- [DisposalScheduleTests.test_actual_question_returns_all_days_without_fragment](C:/sahahaha/tests/test_concise_answers.py:228)
  - 문장/변형: 요일별분리수거뭐해야하는데
- [DisposalScheduleTests.test_specific_day_is_not_answered_with_a_whole_week](C:/sahahaha/tests/test_concise_answers.py:235)
- [DisposalScheduleTests.test_changed_or_duplicate_columns_fail_closed](C:/sahahaha/tests/test_concise_answers.py:241)
- [DisposalScheduleTests.test_stale_schedule_is_not_presented_as_current](C:/sahahaha/tests/test_concise_answers.py:245)
  - 문장/변형: 요일별 분리수거 뭐해야하는데
- [DisposalScheduleTests.test_other_disposal_services_and_time_queries_do_not_use_weekly_table](C:/sahahaha/tests/test_concise_answers.py:254)
  - 문장/변형: 분리수거 몇시에 해?

## test_conjunction_and_deadline_intent.py (5개)

- [ConjunctionAndDeadlineIntentTests.test_location_with_colloquial_conjunction_keeps_both_fields](C:/sahahaha/tests/test_conjunction_and_deadline_intent.py:16)
- [ConjunctionAndDeadlineIntentTests.test_unrelated_words_do_not_become_location_fields](C:/sahahaha/tests/test_conjunction_and_deadline_intent.py:27)
- [ConjunctionAndDeadlineIntentTests.test_numeric_deadline_confirmation_reads_source_value](C:/sahahaha/tests/test_conjunction_and_deadline_intent.py:31)
- [ConjunctionAndDeadlineIntentTests.test_filing_deadline_cannot_use_processing_duration](C:/sahahaha/tests/test_conjunction_and_deadline_intent.py:41)
  - 문장/변형: 신청은 이사 후 20일 이내가 맞나요?
- [ConjunctionAndDeadlineIntentTests.test_duration_incidental_to_documents_does_not_override_field](C:/sahahaha/tests/test_conjunction_and_deadline_intent.py:46)
  - 문장/변형: 전입신고 14일 이내에 낼 준비서류 알려줘
  - 문장/변형: 전입신고 14일 이내 어디로 제출해요?

## test_contact_directory.py (19개)

- [ContactDirectoryTests.test_representative_is_not_head_or_fax](C:/sahahaha/tests/test_contact_directory.py:55)
  - 문장/변형: 건축과 전화번호 알려줘
- [ContactDirectoryTests.test_organization_representative_comes_from_file](C:/sahahaha/tests/test_contact_directory.py:62)
  - 문장/변형: 사하구청 대표번호 알려줘
- [ContactDirectoryTests.test_department_phone_natural_wording](C:/sahahaha/tests/test_contact_directory.py:65)
  - 문장/변형: 건축과 전화번호 좀 알려줘
  - 문장/변형: 건축과 연락처가 어떻게 돼?
  - 문장/변형: 건축과 번호가 뭐야?
  - 문장/변형: 건축과 대표 번호 몇번인가요?
  - 문장/변형: 건축과 전화번호 알려주실 수 있나요?
- [ContactDirectoryTests.test_ai_subject_uses_real_duties](C:/sahahaha/tests/test_contact_directory.py:70)
  - 문장/변형: AI 담당부서 알려줘
- [ContactDirectoryTests.test_alias_is_wording_only](C:/sahahaha/tests/test_contact_directory.py:77)
  - 문장/변형: 보건증을 발급받으려는데 어디에 전화해야하나요?
- [ContactDirectoryTests.test_area_is_not_mistaken_for_department](C:/sahahaha/tests/test_contact_directory.py:81)
- [ContactDirectoryTests.test_multiple_departments_require_choice_with_actual_scopes](C:/sahahaha/tests/test_contact_directory.py:88)
- [ContactDirectoryTests.test_unknown_and_partially_unknown_queries_do_not_guess](C:/sahahaha/tests/test_contact_directory.py:95)
- [ContactDirectoryTests.test_followup_and_clear](C:/sahahaha/tests/test_contact_directory.py:101)
  - 문장/변형: AI 담당부서 알려줘
  - 문장/변형: 보건증 발급 수수료 얼마야?
- [ContactDirectoryTests.test_missing_and_stale_files_fail_closed](C:/sahahaha/tests/test_contact_directory.py:109)
  - 문장/변형: AI 담당부서 알려줘
- [ContactDirectoryTests.test_cache_reloads_changed_file](C:/sahahaha/tests/test_contact_directory.py:119)
- [ContactDirectoryTests.test_personal_info_is_blocked_before_read](C:/sahahaha/tests/test_contact_directory.py:127)
  - 문장/변형: 010-1234-5678로 연락할 보건증 담당 알려줘
- [ContactDirectoryTests.test_non_contact_questions_keep_normal_path](C:/sahahaha/tests/test_contact_directory.py:133)
  - 문장/변형: 여권 수수료 얼마야
  - 문장/변형: 출산지원금 신청 자격 알려줘
- [ContactDirectoryTests.test_excerpt_preserves_parenthesized_regions](C:/sahahaha/tests/test_contact_directory.py:137)
- [ContactDirectoryTests.test_api_contact_route_never_initializes_chatbot](C:/sahahaha/tests/test_contact_directory.py:141)
  - 문장/변형: 건축과 전화번호 알려줘
- [ContactDirectoryTests.test_failed_crawl_does_not_accept_partial_pages](C:/sahahaha/tests/test_contact_directory.py:152)
- [OfficialSnapshotTests.test_various_departments_against_actual_snapshot](C:/sahahaha/tests/test_contact_directory.py:160)
  - 문장/변형: 주차관리과 번호 알려줘
- [OfficialSnapshotTests.test_phone_parser_uses_phone_column_and_both_table_halves](C:/sahahaha/tests/test_contact_directory.py:180)
- [OfficialSnapshotTests.test_official_number_formatting_preserves_digits](C:/sahahaha/tests/test_contact_directory.py:188)

## test_contact_index.py (7개)

- [ContactDirectoryTests.test_office_location_and_contact_is_not_staff_lookup](C:/sahahaha/tests/test_contact_index.py:13)
  - 문장/변형: 사하구청 위치와 연락처 알려줘
- [ContactDirectoryTests.test_dedicated_contact_file_contains_official_records](C:/sahahaha/tests/test_contact_index.py:31)
- [ContactDirectoryTests.test_department_phone_uses_fast_exact_lookup](C:/sahahaha/tests/test_contact_index.py:36)
  - 문장/변형: 자원순환과 전화번호 알려줘
- [ContactDirectoryTests.test_specific_duty_phone_uses_fast_lookup](C:/sahahaha/tests/test_contact_index.py:42)
  - 문장/변형: 대형폐기물 담당자 전화번호 알려줘
- [ContactDirectoryTests.test_ambiguous_duty_asks_for_one_condition](C:/sahahaha/tests/test_contact_index.py:48)
  - 문장/변형: 불법주정차 담당자 전화번호 알려줘
- [ContactDirectoryTests.test_contact_words_without_duty_do_not_guess](C:/sahahaha/tests/test_contact_index.py:54)
  - 문장/변형: 담당자 전화번호 알려줘
- [ContactDirectoryTests.test_clarification_follow_up_resolves_previous_contact_question](C:/sahahaha/tests/test_contact_index.py:58)
  - 문장/변형: 불법주정차 담당자 전화번호 알려줘
  - 문장/변형: 민원처리인지 단속인지 알려주세요

## test_evidence_decision.py (10개)

- [EvidenceDecisionTests.test_hours_and_location_require_both_actual_fields](C:/sahahaha/tests/test_evidence_decision.py:13)
  - 문장/변형: 보건소 진료시간과 위치 알려줘
- [EvidenceDecisionTests.test_missing_location_is_partial_and_not_no_related_source](C:/sahahaha/tests/test_evidence_decision.py:19)
  - 문장/변형: 보건소 시간과 위치 알려줘
- [EvidenceDecisionTests.test_vaccine_eligibility_does_not_establish_place](C:/sahahaha/tests/test_evidence_decision.py:26)
  - 문장/변형: 폐렴구균 접종 장소 알려줘
- [EvidenceDecisionTests.test_high_vector_score_alone_does_not_establish_fire_topic](C:/sahahaha/tests/test_evidence_decision.py:33)
- [EvidenceDecisionTests.test_changed_original_cannot_borrow_old_title](C:/sahahaha/tests/test_evidence_decision.py:39)
- [EvidenceDecisionTests.test_price_without_value_cannot_shortcut_search](C:/sahahaha/tests/test_evidence_decision.py:43)
  - 문장/변형: 대형폐기물 비용 알려줘
- [EvidenceDecisionTests.test_source_update_invalidates_cached_field_coverage](C:/sahahaha/tests/test_evidence_decision.py:47)
- [EvidenceDecisionTests.test_private_or_other_district_source_never_establishes_answer](C:/sahahaha/tests/test_evidence_decision.py:53)
- [EvidenceDecisionTests.test_related_documents_do_not_combine_different_subjects_to_pass](C:/sahahaha/tests/test_evidence_decision.py:58)
- [EvidenceDecisionTests.test_lookup_failure_does_not_claim_that_service_does_not_exist](C:/sahahaha/tests/test_evidence_decision.py:62)

## test_explicit_source_fields.py (4개)

- [ExplicitSourceFieldTests.test_completed_certificate_print_request_keeps_existing_document](C:/sahahaha/tests/test_explicit_source_fields.py:14)
- [ExplicitSourceFieldTests.test_age_question_can_read_explicit_official_screening_criterion](C:/sahahaha/tests/test_explicit_source_fields.py:23)
  - 문장/변형: 주민등록증 신규 발급은 만 몇 세가 대상인가요?
- [ExplicitSourceFieldTests.test_excluded_audience_is_not_a_second_general_audience_request](C:/sahahaha/tests/test_explicit_source_fields.py:31)
  - 문장/변형: 납세자보호관 고충민원 신청 제외대상에 소송 중인 것도 포함되나요?
- [ExplicitSourceFieldTests.test_page_link_does_not_claim_an_unverified_pdf](C:/sahahaha/tests/test_explicit_source_fields.py:39)

## test_free_route_priority.py (7개)

- [FreeRoutePriorityTests.test_request_noun_survives_different_morphological_segmentation](C:/sahahaha/tests/test_free_route_priority.py:21)
  - 문장/변형: 냉장고 무료 방문수거 신청은 어디로 해요?
  - 문장/변형: 냉장고 무상 방문수거는 어디로 신청해요?
- [FreeRoutePriorityTests.test_unrelated_character_fragment_is_not_a_collection_request](C:/sahahaha/tests/test_free_route_priority.py:30)
- [FreeRoutePriorityTests.test_without_reservation_is_a_condition_not_a_cost_question](C:/sahahaha/tests/test_free_route_priority.py:34)
  - 문장/변형: 무료 법률상담은 예약 없이 아무 때나 찾아가면 되나요?
- [FreeRoutePriorityTests.test_explicit_free_route_keeps_exclusion_before_paid_size_fees](C:/sahahaha/tests/test_free_route_priority.py:51)
  - 문장/변형: 냉장고 무료 방문수거 신청은 어디로 해요?
- [FreeRoutePriorityTests.test_complete_source_route_does_not_need_model_selection](C:/sahahaha/tests/test_free_route_priority.py:60)
  - 문장/변형: 냉장고 무료 방문수거 신청은 어디로 해요?
- [FreeRoutePriorityTests.test_other_named_product_cannot_inherit_free_route](C:/sahahaha/tests/test_free_route_priority.py:67)
  - 문장/변형: 냉장고 무료 방문수거 신청은 어디로 해요?
- [FreeRoutePriorityTests.test_paid_fee_question_is_not_silently_changed_to_free_route](C:/sahahaha/tests/test_free_route_priority.py:72)
  - 문장/변형: 냉장고 500ℓ이상 처리 수수료는 얼마인가요?

## test_gemma4_wording_repairs.py (8개)

- [WordingRepairsTests.test_ineligible_source_never_runs_deep_field_extraction](C:/sahahaha/tests/test_gemma4_wording_repairs.py:17)
- [WordingRepairsTests.test_eligible_source_still_requires_requested_field](C:/sahahaha/tests/test_gemma4_wording_repairs.py:28)
- [WordingRepairsTests.test_stated_medication_quantities_are_not_generic_services](C:/sahahaha/tests/test_gemma4_wording_repairs.py:36)
  - 문장/변형: 금연약을 두 알 먹어도 되나요?
  - 문장/변형: 니코틴 패치 한 장 붙이면 되나요?
  - 문장/변형: 금연약 한 알 먹어도 되나요?
- [WordingRepairsTests.test_dose_cannot_be_replaced_by_counseling_and_no_model_is_called](C:/sahahaha/tests/test_gemma4_wording_repairs.py:43)
  - 문장/변형: 금연약을 두 알 먹어도 되나요?
- [WordingRepairsTests.test_live_vacancies_and_static_capacity_or_fees_remain_distinct](C:/sahahaha/tests/test_gemma4_wording_repairs.py:53)
  - 문장/변형: 지금 공영 주차장 남은 칸 알려줘요.
  - 문장/변형: 실시간 공영주차장 잔여 주차면 알려줘
  - 문장/변형: 공영주차장 전체 주차면수 알려줘
  - 문장/변형: 공영주차장 위치 알려줘
- [WordingRepairsTests.test_book_alias_keeps_specific_service_and_quantity](C:/sahahaha/tests/test_gemma4_wording_repairs.py:61)
  - 문장/변형: 작은 도서관 희망책은 한달에 몇권 신청해요?
  - 문장/변형: 작은도서관 희망 책 몇 권 신청할 수 있나요?
- [WordingRepairsTests.test_pending_role_question_can_change_to_adult_renewal](C:/sahahaha/tests/test_gemma4_wording_repairs.py:68)
- [WordingRepairsTests.test_profile_replacement_preserves_new_age_role_and_requested_field](C:/sahahaha/tests/test_gemma4_wording_repairs.py:78)

## test_general_answers.py (24개)

- [GeneralTopicTests.test_passport_spelling_request_does_not_return_a_generic_menu](C:/sahahaha/tests/test_general_answers.py:25)
  - 문장/변형: 여권 영문성명은 어떻게 표기하나요?
- [GeneralTopicTests.test_named_center_is_not_mistaken_for_generic_welfare_support](C:/sahahaha/tests/test_general_answers.py:28)
  - 문장/변형: 사하구 복지 지원 알려줘
- [GeneralTopicTests.test_service_names_survive_morphology](C:/sahahaha/tests/test_general_answers.py:33)
  - 문장/변형: 전입신고 어떻게 해?
- [GeneralTopicTests.test_free_and_no_charge_are_equivalent_for_search_only](C:/sahahaha/tests/test_general_answers.py:37)
- [GeneralTopicTests.test_facility_is_kept_but_request_words_are_not_topics](C:/sahahaha/tests/test_general_answers.py:41)
  - 문장/변형: 사하구청 위치 알려줘
- [GeneralTopicTests.test_missing_service_cannot_be_outvoted_by_conditions](C:/sahahaha/tests/test_general_answers.py:45)
- [GeneralTopicTests.test_health_scope_needs_actual_service_body](C:/sahahaha/tests/test_general_answers.py:49)
- [GeneralTopicTests.test_collective_certificate_name_supports_both](C:/sahahaha/tests/test_general_answers.py:56)
- [GeneralTopicTests.test_benefit_required_certificate_is_not_issuance](C:/sahahaha/tests/test_general_answers.py:61)
- [GeneralTopicTests.test_independent_urls_are_not_crowded_out_by_chunks](C:/sahahaha/tests/test_general_answers.py:65)
- [CrawledSourceTests.test_crawler_original_without_any_embedding_is_searchable](C:/sahahaha/tests/test_general_answers.py:83)
- [CrawledSourceTests.test_stale_external_and_landing_pages_are_excluded](C:/sahahaha/tests/test_general_answers.py:93)
- [CrawledSourceTests.test_misleading_title_cannot_support_an_unrelated_body](C:/sahahaha/tests/test_general_answers.py:99)
- [CrawledSourceTests.test_intent_selection_tries_next_distinct_source](C:/sahahaha/tests/test_general_answers.py:103)
- [GeneralBriefTests.test_free_exclusion_after_product_table_is_retained](C:/sahahaha/tests/test_general_answers.py:120)
- [GeneralBriefTests.test_services_question_uses_actual_contents_not_purpose](C:/sahahaha/tests/test_general_answers.py:127)
- [GeneralBriefTests.test_certificate_method_does_not_select_a_required_card](C:/sahahaha/tests/test_general_answers.py:135)
- [GeneralBriefTests.test_free_collection_retains_damage_exception](C:/sahahaha/tests/test_general_answers.py:140)
- [GeneralBriefTests.test_electronic_application_keeps_channel_and_login](C:/sahahaha/tests/test_general_answers.py:147)
  - 문장/변형: 사하구청에 온라인으로 민원을 신청하려면 어떻게 하나요?
- [GeneralBriefTests.test_wrapped_internet_method_is_complete](C:/sahahaha/tests/test_general_answers.py:153)
- [GeneralBriefTests.test_short_frequency_question_uses_frequency_not_another_field](C:/sahahaha/tests/test_general_answers.py:160)
  - 문장/변형: 정화조는 얼마나 자주 청소해야 하나요?
- [GeneralBriefTests.test_clear_method_request_does_not_ask_to_choose_method_again](C:/sahahaha/tests/test_general_answers.py:166)
  - 문장/변형: 전입신고 방법 알려줘
- [GeneralBriefTests.test_flat_money_cells_are_not_reassigned_to_a_subject](C:/sahahaha/tests/test_general_answers.py:170)
  - 문장/변형: 여권 수수료 얼마야
- [GeneralBriefTests.test_source_details_and_exception_remain_intact](C:/sahahaha/tests/test_general_answers.py:175)

## test_generalization_repairs.py (34개)

- [SafetyGeneralizationTests.test_age_and_duration_are_not_private_addresses](C:/sahahaha/tests/test_generalization_repairs.py:12)
  - 문장/변형: 다대포 축구장을 빌리면 2시간 사용료가 얼마예요?
- [SafetyGeneralizationTests.test_private_street_lot_and_mobile_numbers_still_block](C:/sahahaha/tests/test_generalization_repairs.py:18)
- [SafetyGeneralizationTests.test_smoke_at_a_factory_gets_immediate_emergency_guidance](C:/sahahaha/tests/test_generalization_repairs.py:23)
- [SafetyGeneralizationTests.test_schedule_postponement_is_not_a_fire](C:/sahahaha/tests/test_generalization_repairs.py:28)
- [GeneralSourceTests.test_active_headings_do_not_inherit_previous_sibling_service](C:/sahahaha/tests/test_generalization_repairs.py:34)
- [GeneralSourceTests.test_all_requirements_survive_intermediate_field_headings](C:/sahahaha/tests/test_generalization_repairs.py:40)
- [GeneralSourceTests.test_national_telephone_program_does_not_enrich_local_clinic](C:/sahahaha/tests/test_generalization_repairs.py:48)
- [GeneralSourceTests.test_official_numbered_formula_remains_complete](C:/sahahaha/tests/test_generalization_repairs.py:55)
- [GeneralSourceTests.test_table_item_size_and_total_are_not_detached](C:/sahahaha/tests/test_generalization_repairs.py:62)
  - 문장/변형: 대형폐기물 2인용 소파 비용 얼마야?
- [GeneralSourceTests.test_bundled_panel_cannot_establish_standalone_test_price](C:/sahahaha/tests/test_generalization_repairs.py:71)
- [GeneralSourceTests.test_provider_checkbox_does_not_remove_cancer_age_and_period](C:/sahahaha/tests/test_generalization_repairs.py:78)
  - 문장/변형: 국가암검진 위암 몇 살부터 몇 년마다?
- [GeneralSourceTests.test_all_people_condition_uses_actual_target_row_instead_of_provider_note](C:/sahahaha/tests/test_generalization_repairs.py:87)
- [GeneralSourceTests.test_processing_time_is_not_opening_hours](C:/sahahaha/tests/test_generalization_repairs.py:94)
- [GeneralSourceTests.test_short_certificate_reply_preserves_exemption_profile](C:/sahahaha/tests/test_generalization_repairs.py:100)
- [GeneralSourceTests.test_missing_location_does_not_erase_available_registration_documents](C:/sahahaha/tests/test_generalization_repairs.py:107)
- [GeneralSourceTests.test_audience_comparison_keeps_cutoff_and_does_not_choose_other_column](C:/sahahaha/tests/test_generalization_repairs.py:116)
- [GeneralSourceTests.test_snapshot_search_reads_actual_html_table_and_avoids_reparse](C:/sahahaha/tests/test_generalization_repairs.py:125)
- [GeneralSourceTests.test_failed_initial_snapshot_retries_without_caching_empty_result](C:/sahahaha/tests/test_generalization_repairs.py:140)
- [GeneralSourceTests.test_bulleted_all_requirements_survive_model_selection](C:/sahahaha/tests/test_generalization_repairs.py:155)
- [GeneralSourceTests.test_requested_detail_precedes_another_programs_field_coverage](C:/sahahaha/tests/test_generalization_repairs.py:164)
  - 문장/변형: 임산부 철분제는 몇 주부터 얼마나 받을 수 있어요?
- [GeneralSourceTests.test_source_definition_without_question_mark_and_income_comparison](C:/sahahaha/tests/test_generalization_repairs.py:174)
- [GeneralSourceTests.test_method_fallback_never_uses_marketing_or_phone_as_procedure](C:/sahahaha/tests/test_generalization_repairs.py:187)
  - 문장/변형: 형광등 어디에 버려야 해?
- [GeneralSourceTests.test_age_transition_is_not_answered_with_general_eligibility](C:/sahahaha/tests/test_generalization_repairs.py:200)
- [GeneralSourceTests.test_named_program_audience_does_not_require_repeating_generic_patient_name](C:/sahahaha/tests/test_generalization_repairs.py:208)
  - 문장/변형: 영양플러스는 임산부만 대상인가요?
- [GeneralSourceTests.test_regular_tax_period_excludes_optional_annual_payment](C:/sahahaha/tests/test_generalization_repairs.py:219)
  - 문장/변형: 자동차세 보통 몇 월에 내요?
- [GeneralSourceTests.test_area_selects_own_program_and_frequency](C:/sahahaha/tests/test_generalization_repairs.py:227)
- [GeneralSourceTests.test_incidental_service_mention_does_not_become_its_guide](C:/sahahaha/tests/test_generalization_repairs.py:235)
- [GeneralSourceTests.test_missing_detail_cannot_fall_back_to_service_introduction](C:/sahahaha/tests/test_generalization_repairs.py:241)
- [GeneralSourceTests.test_contact_clarification_keeps_reporting_intent](C:/sahahaha/tests/test_generalization_repairs.py:248)
  - 문장/변형: 신고 전화번호 알려줘
  - 문장/변형: 문의할 업무나 부서명을 알려주세요.
- [GeneralSourceTests.test_long_condition_reply_preserves_program_but_new_topic_is_separate](C:/sahahaha/tests/test_generalization_repairs.py:256)
  - 문장/변형: 여권 사진 몇 장이에요?
- [GeneralContactTests.test_inspection_and_health_organization_scope](C:/sahahaha/tests/test_generalization_repairs.py:265)
- [ReportFactsTests.test_count_uses_requested_year_and_column](C:/sahahaha/tests/test_generalization_repairs.py:293)
  - 문장/변형: 정보공개청구 보고서에서 2025년 청구 건수는 몇 건인가요?
- [ReportFactsTests.test_current_and_conflicting_counts_are_not_guessed](C:/sahahaha/tests/test_generalization_repairs.py:301)
  - 문장/변형: 정보공개청구 보고서에서 2025년 청구 건수는 몇 건인가요?
  - 문장/변형: 정보공개청구 보고서에서 올해 청구 건수는 몇 건인가요?
- [ReportFactsTests.test_data_period_is_distinct_from_issued_date](C:/sahahaha/tests/test_generalization_repairs.py:307)
  - 문장/변형: 정보공개청구 보고서는 몇 년 자료를 분석했나요?

## test_grounded_planner.py (14개)

- [GroundedPlannerTests.test_scoped_course_asks_about_audience_before_presenting_venue](C:/sahahaha/tests/test_grounded_planner.py:18)
  - 문장/변형: 소방 안전 교육 어디서 들어
- [GroundedPlannerTests.test_confirmed_audience_does_not_turn_planned_venue_into_confirmed_venue](C:/sahahaha/tests/test_grounded_planner.py:26)
  - 문장/변형: 공동주택 소방 안전 교육 어디서 들어
- [GroundedPlannerTests.test_venue_from_next_course_is_rejected_even_on_same_page](C:/sahahaha/tests/test_grounded_planner.py:34)
  - 문장/변형: 소방 안전 교육 어디서 들어
- [GroundedPlannerTests.test_exception_is_kept_without_model_having_to_select_it](C:/sahahaha/tests/test_grounded_planner.py:41)
- [GroundedPlannerTests.test_invented_text_ids_and_incomplete_units_cannot_enter_answer](C:/sahahaha/tests/test_grounded_planner.py:47)
- [GroundedPlannerTests.test_answer_requires_the_requested_field](C:/sahahaha/tests/test_grounded_planner.py:53)
- [GroundedPlannerTests.test_model_failure_uses_fallback_contract](C:/sahahaha/tests/test_grounded_planner.py:57)
- [GroundedPlannerTests.test_normal_question_actually_calls_model_and_uses_selected_fact](C:/sahahaha/tests/test_grounded_planner.py:63)
- [GroundedPlannerTests.test_source_only_fallback_keeps_course_scope](C:/sahahaha/tests/test_grounded_planner.py:72)
  - 문장/변형: 소방 안전 교육 어디서 들어
- [GroundedPlannerTests.test_portal_printing_conditions_are_not_candidates_for_move_report](C:/sahahaha/tests/test_grounded_planner.py:81)
  - 문장/변형: 전입신고 어떻게 해?
- [GroundedPlannerTests.test_frequency_question_cannot_answer_with_fee_calculator](C:/sahahaha/tests/test_grounded_planner.py:87)
  - 문장/변형: 정화조 청소 얼마나 자주 해야 해?
- [GroundedPlannerTests.test_general_resident_condition_does_not_erase_general_waste_topic](C:/sahahaha/tests/test_grounded_planner.py:94)
- [GroundedPlannerTests.test_model_context_budget_does_not_drop_hidden_exception_from_answer](C:/sahahaha/tests/test_grounded_planner.py:101)
- [GroundedPlannerTests.test_course_yes_no_replies_keep_confirmed_scope_without_repeating_question](C:/sahahaha/tests/test_grounded_planner.py:109)
  - 문장/변형: 소방 안전 교육 어디서 들어

## test_institution_and_field_scope.py (8개)

- [InstitutionAndFieldScopeTests.test_office_address_and_phone_are_one_institution_topic](C:/sahahaha/tests/test_institution_and_field_scope.py:18)
- [InstitutionAndFieldScopeTests.test_other_facility_address_cannot_locate_office](C:/sahahaha/tests/test_institution_and_field_scope.py:27)
- [InstitutionAndFieldScopeTests.test_fabricated_congratulatory_grant_cannot_borrow_birth_policy](C:/sahahaha/tests/test_institution_and_field_scope.py:32)
  - 문장/변형: 사하구 새가족우주축하금 99만원 신청 방법 알려줘.
  - 문장/변형: 출산지원금 신청 방법 알려줘.
- [InstitutionAndFieldScopeTests.test_income_percentage_keeps_all_eligibility_requirements](C:/sahahaha/tests/test_institution_and_field_scope.py:37)
  - 문장/변형: 임신부 영양플러스 신청 소득 기준이 몇 퍼센트인지 알려줘.
- [InstitutionAndFieldScopeTests.test_meaning_word_is_a_requested_field_not_an_unknown_entity](C:/sahahaha/tests/test_institution_and_field_scope.py:45)
  - 문장/변형: 행정서비스헌장의 의미가 뭔지 알고 싶어요.
- [InstitutionAndFieldScopeTests.test_explicit_youth_visit_reservation_matches_its_program](C:/sahahaha/tests/test_institution_and_field_scope.py:52)
- [InstitutionAndFieldScopeTests.test_general_public_education_does_not_need_audience_confirmation](C:/sahahaha/tests/test_institution_and_field_scope.py:60)
- [InstitutionAndFieldScopeTests.test_eligibility_keeps_same_program_financial_restriction](C:/sahahaha/tests/test_institution_and_field_scope.py:68)
  - 문장/변형: 마을세무사 이용 대상이 누구인가요?

## test_llm_runtime.py (10개)

- [ModelRuntimeTests.test_translation_preserves_schema_tokens_nonstream_and_no_thought](C:/sahahaha/tests/test_llm_runtime.py:20)
- [ModelRuntimeTests.test_length_finish_is_preserved_for_planner_to_reject](C:/sahahaha/tests/test_llm_runtime.py:46)
- [ModelRuntimeTests.test_backend_error_body_never_in_application_exception](C:/sahahaha/tests/test_llm_runtime.py:54)
- [ModelRuntimeTests.test_tool_or_reasoning_only_output_is_not_a_fact](C:/sahahaha/tests/test_llm_runtime.py:60)
- [ModelRuntimeTests.test_missing_schema_never_sends_unconstrained_prompt](C:/sahahaha/tests/test_llm_runtime.py:70)
- [ModelRuntimeTests.test_url_configuration_rejects_embedded_credentials](C:/sahahaha/tests/test_llm_runtime.py:76)
- [ModelRuntimeTests.test_vllm_factory_and_status_never_need_ollama](C:/sahahaha/tests/test_llm_runtime.py:83)
- [ModelRuntimeTests.test_wrong_model_and_auth_failure_are_not_ready](C:/sahahaha/tests/test_llm_runtime.py:97)
- [ModelRuntimeTests.test_provider_endpoint_and_model_switch_invalidate_plan_cache](C:/sahahaha/tests/test_llm_runtime.py:106)
- [ModelRuntimeTests.test_local_gemma4_requests_no_thinking_and_configured_context](C:/sahahaha/tests/test_llm_runtime.py:113)

## test_local_inference.py (5개)

- [LocalInferenceTests.test_exact_payload_and_structured_metadata_are_kept](C:/sahahaha/tests/test_local_inference.py:30)
- [LocalInferenceTests.test_timeout_cancels_pending_await_closes_client_and_releases_slot](C:/sahahaha/tests/test_local_inference.py:44)
- [LocalInferenceTests.test_busy_model_is_not_submitted_to_backend_queue](C:/sahahaha/tests/test_local_inference.py:66)
- [LocalInferenceTests.test_model_weight_change_and_unknown_revision_do_not_reuse_selection](C:/sahahaha/tests/test_local_inference.py:75)
- [LocalInferenceTests.test_operational_failure_is_not_reported_as_missing_source](C:/sahahaha/tests/test_local_inference.py:85)

## test_merge_integration.py (11개)

- [MergeIntegrationTests.test_faq_alias_selects_current_original_instead_of_draft_answer](C:/sahahaha/tests/test_merge_integration.py:20)
  - 문장/변형: 작은도서관 교육 프로그램 예약 방법 알려줘
- [MergeIntegrationTests.test_original_table_text_and_structured_search_chunks_coexist](C:/sahahaha/tests/test_merge_integration.py:37)
- [MergeIntegrationTests.test_missing_html_column_falls_back_without_hiding_other_errors](C:/sahahaha/tests/test_merge_integration.py:51)
- [MergeIntegrationTests.test_text_only_refresh_does_not_erase_saved_html](C:/sahahaha/tests/test_merge_integration.py:64)
- [MergeIntegrationTests.test_compound_office_question_reaches_original_page_route](C:/sahahaha/tests/test_merge_integration.py:68)
  - 문장/변형: 사하구청 위치와 연락처 알려줘
- [MergeIntegrationTests.test_compound_location_keeps_facility_instead_of_generic_location_word](C:/sahahaha/tests/test_merge_integration.py:74)
  - 문장/변형: 사하구청 위치와 연락처 알려줘
- [MergeIntegrationTests.test_library_program_cannot_borrow_smoking_education_instructions](C:/sahahaha/tests/test_merge_integration.py:79)
  - 문장/변형: 작은도서관 교육 프로그램 예약 방법 알려줘
- [MergeIntegrationTests.test_general_resident_course_does_not_repeat_an_audience_question](C:/sahahaha/tests/test_merge_integration.py:84)
  - 문장/변형: 소방 안전 교육 어디서 들어
- [MergeIntegrationTests.test_faq_draft_is_not_official_evidence_just_because_it_has_an_official_url](C:/sahahaha/tests/test_merge_integration.py:88)
  - 문장/변형: 사하구청 대표전화 알려줘
- [MergeIntegrationTests.test_priority_sources_are_refreshed_without_a_private_workbook](C:/sahahaha/tests/test_merge_integration.py:93)
- [MergeIntegrationTests.test_new_catalogue_landing_pages_are_not_specific_service_instructions](C:/sahahaha/tests/test_merge_integration.py:102)

## test_metadata_provider.py (5개)

- [TaggingProviderTests.test_busy_batch_preserves_source_metadata_without_per_chunk_retries](C:/sahahaha/tests/test_metadata_provider.py:17)
- [TaggingProviderTests.test_vllm_single_and_batch_use_provider_schema_without_ollama](C:/sahahaha/tests/test_metadata_provider.py:29)
- [TaggingProviderTests.test_tags_cannot_override_source_identity](C:/sahahaha/tests/test_metadata_provider.py:50)
- [TaggingProviderTests.test_unavailable_model_preserves_raw_metadata_and_keywords](C:/sahahaha/tests/test_metadata_provider.py:58)
- [TaggingProviderTests.test_backend_error_uses_raw_fallback_without_auth_log](C:/sahahaha/tests/test_metadata_provider.py:67)

## test_official_content.py (40개)

- [OfficialContentTests.test_free_consultation_availability_keeps_explicit_free_proof](C:/sahahaha/tests/test_official_content.py:15)
- [OfficialContentTests.test_program_operation_question_requests_actual_services](C:/sahahaha/tests/test_official_content.py:21)
- [OfficialContentTests.test_support_list_names_only_requested_whole_items](C:/sahahaha/tests/test_official_content.py:28)
- [OfficialContentTests.test_support_percentage_keeps_same_program_ceiling](C:/sahahaha/tests/test_official_content.py:36)
  - 문장/변형: 고위험 임산부 의료비는 얼마나 지원받을 수 있나요?
- [OfficialContentTests.test_support_heading_preserves_nested_amount_label](C:/sahahaha/tests/test_official_content.py:44)
- [OfficialContentTests.test_all_required_eligibility_rows_remain_with_intro](C:/sahahaha/tests/test_official_content.py:51)
- [OfficialContentTests.test_online_certificate_keeps_method_and_normal_result_condition](C:/sahahaha/tests/test_official_content.py:57)
- [OfficialContentTests.test_factual_h_tag_keeps_clinic_scope_and_usage_conditions](C:/sahahaha/tests/test_official_content.py:64)
- [OfficialContentTests.test_publication_question_does_not_select_appeal_period](C:/sahahaha/tests/test_official_content.py:72)
  - 문장/변형: 개별주택가격과 공동주택가격은 언제 공시되나요?
- [OfficialContentTests.test_automatic_insurance_registration_answers_necessity](C:/sahahaha/tests/test_official_content.py:79)
- [OfficialContentTests.test_spaced_target_and_participation_condition_are_fields](C:/sahahaha/tests/test_official_content.py:85)
- [OfficialContentTests.test_request_format_and_symptom_do_not_erase_service_subject](C:/sahahaha/tests/test_official_content.py:90)
  - 문장/변형: 보건소 각종 검사 비용은 어디에서 확인하나요?
- [OfficialContentTests.test_statutory_classes_establish_legal_infection_topic](C:/sahahaha/tests/test_official_content.py:96)
- [OfficialContentTests.test_facility_rows_filter_selected_dong](C:/sahahaha/tests/test_official_content.py:101)
  - 문장/변형: 당리동 민방위 시설은 어디에 있나요?
- [OfficialContentTests.test_missing_area_cannot_fall_back_to_first_facility_row](C:/sahahaha/tests/test_official_content.py:107)
  - 문장/변형: 감천동 민방위 시설 어디에 있나요?
- [OfficialContentTests.test_html_column_missing_retries_only_the_legacy_fields](C:/sahahaha/tests/test_official_content.py:114)
- [OfficialContentTests.test_network_error_is_not_retried_as_a_schema_problem](C:/sahahaha/tests/test_official_content.py:128)
- [OfficialContentTests.test_certificate_availability_answers_service_instead_of_authentication](C:/sahahaha/tests/test_official_content.py:137)
- [OfficialContentTests.test_tax_eligibility_recognizes_the_taxpayer_label](C:/sahahaha/tests/test_official_content.py:142)
- [OfficialContentTests.test_question_heading_is_not_a_fact_and_definition_is_labelled](C:/sahahaha/tests/test_official_content.py:148)
- [OfficialContentTests.test_definition_does_not_select_application_consent_document](C:/sahahaha/tests/test_official_content.py:153)
- [OfficialContentTests.test_service_title_owns_all_of_its_fields](C:/sahahaha/tests/test_official_content.py:157)
  - 문장/변형: 영양플러스 대상은 누구인가요?
- [OfficialContentTests.test_a_table_wrapper_is_not_duplicated_as_flat_prose](C:/sahahaha/tests/test_official_content.py:162)
- [OfficialContentTests.test_fee_question_does_not_scope_to_short_parking_definition](C:/sahahaha/tests/test_official_content.py:166)
- [OfficialContentTests.test_missing_clear_html_field_is_not_a_redundant_clarification](C:/sahahaha/tests/test_official_content.py:172)
- [OfficialContentTests.test_reviewed_dates_are_quarantined_until_the_page_changes](C:/sahahaha/tests/test_official_content.py:178)
- [OfficialContentTests.test_old_invitation_warning_excludes_historical_reference_dates](C:/sahahaha/tests/test_official_content.py:187)
- [OfficialContentTests.test_age_range_stays_in_its_own_program_row](C:/sahahaha/tests/test_official_content.py:192)
  - 문장/변형: 아이돌봄은 몇 살까지 이용하나요?
- [OfficialContentTests.test_disability_pension_preserves_both_conditions](C:/sahahaha/tests/test_official_content.py:199)
- [OfficialContentTests.test_job_seeker_does_not_select_employer_registration](C:/sahahaha/tests/test_official_content.py:206)
  - 문장/변형: 구직 등록은 어떻게 하나요?
- [OfficialContentTests.test_repeated_fields_in_different_services_are_preserved](C:/sahahaha/tests/test_official_content.py:214)
- [OfficialContentTests.test_row_span_prices_keep_the_same_owner](C:/sahahaha/tests/test_official_content.py:220)
- [OfficialContentTests.test_vertical_th_cells_are_labels_not_column_headers](C:/sahahaha/tests/test_official_content.py:225)
- [OfficialContentTests.test_embedded_board_does_not_hide_real_tb_service](C:/sahahaha/tests/test_official_content.py:231)
- [OfficialContentTests.test_html_notice_table_is_excluded](C:/sahahaha/tests/test_official_content.py:237)
- [OfficialContentTests.test_bicycle_rental_cannot_use_waste_free_pickup](C:/sahahaha/tests/test_official_content.py:241)
- [OfficialContentTests.test_heading_is_not_a_model_fact](C:/sahahaha/tests/test_official_content.py:245)
  - 문장/변형: 지원금액 얼마인가요?
- [OfficialContentTests.test_official_numeric_url_identifiers_survive_output_mask](C:/sahahaha/tests/test_official_content.py:249)
- [OfficialContentTests.test_url_cannot_hide_pii_in_unrecognized_query_param](C:/sahahaha/tests/test_official_content.py:255)
- [OfficialContentTests.test_compound_target_and_documents_keeps_both_fields](C:/sahahaha/tests/test_official_content.py:261)

## test_official_faq.py (18개)

- [OfficialFaqTests.test_all_100_official_questions_match_their_approved_answer](C:/sahahaha/tests/test_official_faq.py:23)
- [OfficialFaqTests.test_every_official_question_has_unique_source_url](C:/sahahaha/tests/test_official_faq.py:32)
- [OfficialFaqTests.test_priority_variants_match_expected_official_questions](C:/sahahaha/tests/test_official_faq.py:37)
  - 문장/변형: 구청 대표 번호 뭐야?
  - 문장/변형: 대형 쓰레기 버리는 법 알려줘
  - 문장/변형: 보건소 몇 시에 열어요?
  - 문장/변형: 성인 예방접종 시간 알려줘
- [OfficialFaqTests.test_broad_health_word_is_not_a_direct_official_answer](C:/sahahaha/tests/test_official_faq.py:50)
- [OfficialFaqTests.test_location_and_contact_query_retrieves_both_official_answers](C:/sahahaha/tests/test_official_faq.py:53)
  - 문장/변형: 사하구청 위치와 연락처 알려줘
- [OfficialFaqTests.test_official_faq_source_does_not_inherit_unrelated_staff_contact](C:/sahahaha/tests/test_official_faq.py:63)
  - 문장/변형: 사하구청 위치와 연락처 알려줘
- [OfficialFaqTests.test_resource_contains_no_missing_answer_or_url](C:/sahahaha/tests/test_official_faq.py:74)
- [OfficialFaqTests.test_priority_service_variants_match_verified_sources](C:/sahahaha/tests/test_official_faq.py:78)
  - 문장/변형: 일반쓰레기 음식물쓰레기 재활용품의 요일별 배출 방법 알려줘
  - 문장/변형: 소방특화 들락날락 체험은 어떻게 예약해?
  - 문장/변형: 작은도서관 교육 프로그램 예약 방법 알려줘
  - 문장/변형: 사하구보건소 몇 시에 문 열어?
- [StructuredHtmlTests.test_heading_and_table_relationship_are_preserved](C:/sahahaha/tests/test_official_faq.py:94)
- [DomainClarificationTests.test_generic_waste_question_answers_before_clarifying](C:/sahahaha/tests/test_official_faq.py:119)
  - 문장/변형: 쓰레기 배출 알려줘
- [DomainClarificationTests.test_specific_food_waste_question_does_not_repeat_clarification](C:/sahahaha/tests/test_official_faq.py:122)
- [DomainClarificationTests.test_generic_reservation_question_asks_for_the_actual_program](C:/sahahaha/tests/test_official_faq.py:125)
  - 문장/변형: 예약하고 싶어요
- [DomainClarificationTests.test_generic_health_question_answers_before_clarifying](C:/sahahaha/tests/test_official_faq.py:128)
  - 문장/변형: 보건소 이용하고 싶어요
- [DomainClarificationTests.test_generic_contact_question_asks_for_duty](C:/sahahaha/tests/test_official_faq.py:131)
  - 문장/변형: 담당자 전화번호 알려줘
- [DomainClarificationTests.test_office_location_and_contact_does_not_ask_for_duty](C:/sahahaha/tests/test_official_faq.py:136)
  - 문장/변형: 사하구청 위치와 연락처 알려줘
- [DomainClarificationTests.test_broad_welfare_question_preserves_user_scope_policy](C:/sahahaha/tests/test_official_faq.py:139)
  - 문장/변형: 복지 지원 알려줘
- [DomainClarificationTests.test_specific_welfare_question_skips_clarification](C:/sahahaha/tests/test_official_faq.py:144)
  - 문장/변형: 한부모가족 지원 알려줘
- [DomainClarificationTests.test_broad_tax_question_answers_with_overview](C:/sahahaha/tests/test_official_faq.py:147)

## test_online_location_and_day_fields.py (5개)

- [OnlineLocationAndDayFieldTests.test_online_application_where_is_a_channel_not_a_physical_place](C:/sahahaha/tests/test_online_location_and_day_fields.py:14)
  - 문장/변형: 보건증 검사를 받았어요. 인터넷 발급 홈페이지가 어디인가요?
- [OnlineLocationAndDayFieldTests.test_online_word_does_not_erase_explicit_physical_visit_location](C:/sahahaha/tests/test_online_location_and_day_fields.py:23)
  - 문장/변형: 인터넷 예약한 보건소의 실제 방문 주소는 어디인가요?
  - 문장/변형: 온라인 신청 후 현장 접수 장소는 어디인가요?
- [OnlineLocationAndDayFieldTests.test_road_address_is_a_field_not_a_second_unknown_facility](C:/sahahaha/tests/test_online_location_and_day_fields.py:27)
- [OnlineLocationAndDayFieldTests.test_spaced_day_question_selects_actual_decision_duration](C:/sahahaha/tests/test_online_location_and_day_fields.py:34)
  - 문장/변형: 몇 일
  - 문장/변형: 몇일
- [OnlineLocationAndDayFieldTests.test_missing_field_cannot_borrow_from_another_named_program](C:/sahahaha/tests/test_online_location_and_day_fields.py:44)
  - 문장/변형: 금연클리닉 비용이 얼마인가요?

## test_passport_documents.py (11개)

- [PassportDocumentsTests.test_renewal_reads_current_documents_and_existing_passport](C:/sahahaha/tests/test_passport_documents.py:46)
  - 문장/변형: 성인 여권 재발급 준비물 알려줘
- [PassportDocumentsTests.test_parent_and_self_documents_are_separate_after_html_joining](C:/sahahaha/tests/test_passport_documents.py:54)
- [PassportDocumentsTests.test_relative_requires_adult_second_degree_and_authorization](C:/sahahaha/tests/test_passport_documents.py:64)
- [PassportDocumentsTests.test_age_and_role_followups_keep_the_renewal_request](C:/sahahaha/tests/test_passport_documents.py:70)
  - 문장/변형: 부모가 청소년 여권 재발급 준비하려는데 서류 알려줘
- [PassportDocumentsTests.test_parent_reply_without_age_keeps_asking_age_not_issuing_adult_list](C:/sahahaha/tests/test_passport_documents.py:80)
- [PassportDocumentsTests.test_explicit_age_is_not_overridden_by_adult_visitor_word](C:/sahahaha/tests/test_passport_documents.py:88)
- [PassportDocumentsTests.test_legacy_lines_and_edited_source_values_are_read_not_fixed](C:/sahahaha/tests/test_passport_documents.py:93)
- [PassportDocumentsTests.test_missing_visitor_boundary_abstains_instead_of_mixing_lists](C:/sahahaha/tests/test_passport_documents.py:98)
- [PassportDocumentsTests.test_old_page_abstains_and_does_not_expose_verified_status](C:/sahahaha/tests/test_passport_documents.py:103)
- [PassportDocumentsTests.test_current_page_keeps_source_and_folded_full_original](C:/sahahaha/tests/test_passport_documents.py:110)
- [PassportDocumentsTests.test_collection_and_special_applications_do_not_use_visit_application_list](C:/sahahaha/tests/test_passport_documents.py:119)

## test_payment_and_communication_intent.py (5개)

- [PaymentAndCommunicationIntentTests.test_communication_alternatives_skip_employee_number_lookup](C:/sahahaha/tests/test_payment_and_communication_intent.py:14)
  - 문장/변형: 상담을 팩스 대신 이메일로 할 수 있는 방법 알려줘
- [PaymentAndCommunicationIntentTests.test_explicit_number_still_uses_contact_lookup](C:/sahahaha/tests/test_payment_and_communication_intent.py:21)
  - 문장/변형: 마을세무사 담당부서 전화번호 알려줘
  - 문장/변형: 전화 상담 방법이랑 담당부서 전화번호 알려줘
- [PaymentAndCommunicationIntentTests.test_actual_payment_mode_is_not_an_eligibility_question](C:/sahahaha/tests/test_payment_and_communication_intent.py:26)
- [PaymentAndCommunicationIntentTests.test_negated_free_service_is_a_real_exclusion](C:/sahahaha/tests/test_payment_and_communication_intent.py:35)
  - 문장/변형: 부품 탈취된 냉장고는 무상수거 제외 품목인가요?
- [PaymentAndCommunicationIntentTests.test_amount_field_does_not_produce_false_unknown_detail](C:/sahahaha/tests/test_payment_and_communication_intent.py:40)
  - 문장/변형: 고향사랑기부금 답례품은 기부금액의 몇 퍼센트 이내예요?

## test_priority_guard.py (3개)

- [PriorityGuardTests.test_keeps_complete_llm_answer](C:/sahahaha/tests/test_priority_guard.py:17)
- [PriorityGuardTests.test_replaces_incomplete_llm_answer](C:/sahahaha/tests/test_priority_guard.py:25)
- [PriorityGuardTests.test_does_not_change_normal_answer](C:/sahahaha/tests/test_priority_guard.py:34)

## test_query_field_routes.py (12개)

- [QueryFieldRouteTests.test_compound_hours_address_keeps_both_facts](C:/sahahaha/tests/test_query_field_routes.py:24)
  - 문장/변형: 보건소가 몇 시부터 몇 시까지 진료하고 어느 주소에 있나요?
- [QueryFieldRouteTests.test_short_service_words_are_not_accidental_character_joins](C:/sahahaha/tests/test_query_field_routes.py:31)
  - 문장/변형: 몇 시까지 진료하나요?
  - 문장/변형: 구인 정보 알려줘
- [QueryFieldRouteTests.test_filing_deadline_is_not_processing_time](C:/sahahaha/tests/test_query_field_routes.py:38)
- [QueryFieldRouteTests.test_youth_in_person_reservation_is_not_telephone_program](C:/sahahaha/tests/test_query_field_routes.py:43)
- [QueryFieldRouteTests.test_free_pickup_contact_is_a_service_channel_not_address](C:/sahahaha/tests/test_query_field_routes.py:50)
  - 문장/변형: 멀쩡한 냉장고를 돈 안 내고 수거 요청하려면 어디로 연락하나요?
- [QueryFieldRouteTests.test_communication_method_does_not_enter_employee_lookup](C:/sahahaha/tests/test_query_field_routes.py:58)
- [QueryFieldRouteTests.test_labelled_limit_is_complete_but_unfinished_verb_is_not](C:/sahahaha/tests/test_query_field_routes.py:65)
  - 문장/변형: 희망도서를 신청만 하고 계속 빌려가지 않으면 신청이 제한되나요?
- [QueryFieldRouteTests.test_pending_court_case_selects_actual_exclusion](C:/sahahaha/tests/test_query_field_routes.py:74)
  - 문장/변형: 납세자보호관에게 법원에서 이미 진행 중인 건도 고충민원으로 내도 되나요?
- [QueryFieldRouteTests.test_gift_percentage_is_not_tax_deduction](C:/sahahaha/tests/test_query_field_routes.py:81)
  - 문장/변형: 고향사랑기부 답례품은 기부금의 몇 퍼센트까지 주나요?
- [QueryFieldRouteTests.test_explicit_applicant_keeps_common_documents_and_own_row](C:/sahahaha/tests/test_query_field_routes.py:86)
- [QueryFieldRouteTests.test_decision_extension_keeps_deadline_and_written_notice](C:/sahahaha/tests/test_query_field_routes.py:94)
  - 문장/변형: 정보공개 결정을 연장할 수도 있나요? 연장하면 청구인에게 알려주나요?
- [QueryFieldRouteTests.test_current_waiting_count_has_no_fabricated_population](C:/sahahaha/tests/test_query_field_routes.py:101)
  - 문장/변형: 지금 영양플러스 신청 대기 인원이 정확히 몇 명인지 알려줘.
  - 문장/변형: 영양플러스 신청 인원 선정기준 알려줘

## test_question_intent.py (14개)

- [OpeningHoursTests.test_reported_query_returns_hours_lunch_and_early_arrival_condition](C:/sahahaha/tests/test_question_intent.py:24)
  - 문장/변형: 보건소 여는시간 알려줘
- [OpeningHoursTests.test_colloquial_opening_and_closing_queries_use_same_verified_hours](C:/sahahaha/tests/test_question_intent.py:32)
  - 문장/변형: 보건소 몇시에 열어?
  - 문장/변형: 보건소 몇시까지 해?
  - 문장/변형: 사하구 보건소 운영시간 알려줘
- [OpeningHoursTests.test_short_numeric_hours_are_not_discarded](C:/sahahaha/tests/test_question_intent.py:40)
- [OpeningHoursTests.test_clock_colons_do_not_split_a_label_from_its_value](C:/sahahaha/tests/test_question_intent.py:45)
- [OpeningHoursTests.test_new_source_field_is_not_merged_into_an_empty_label](C:/sahahaha/tests/test_question_intent.py:51)
- [OpeningHoursTests.test_address_only_source_cannot_answer_an_hours_question](C:/sahahaha/tests/test_question_intent.py:55)
- [OpeningHoursTests.test_address_query_still_selects_address](C:/sahahaha/tests/test_question_intent.py:60)
  - 문장/변형: 보건소 위치 알려줘
- [OpeningHoursTests.test_operating_hours_and_processing_duration_are_distinct](C:/sahahaha/tests/test_question_intent.py:66)
  - 문장/변형: 보건소 몇 시까지 해?
- [OpeningHoursTests.test_search_subject_does_not_require_literal_operating_word](C:/sahahaha/tests/test_question_intent.py:72)
  - 문장/변형: 보건소 여는시간 알려줘
  - 문장/변형: 사하구 보건소 운영시간 알려줘
  - 문장/변형: 보건소 몇시까지 해?
- [OpeningHoursTests.test_time_wording_does_not_remove_part_of_a_facility_name](C:/sahahaha/tests/test_question_intent.py:76)
  - 문장/변형: 구민문화회관 운영시간 알려줘
- [OpeningHoursTests.test_generic_health_hours_select_health_center_not_village_center](C:/sahahaha/tests/test_question_intent.py:80)
  - 문장/변형: 보건소 여는시간 알려줘
  - 문장/변형: 보건소 몇시에 열어?
  - 문장/변형: 보건소 몇시까지 해?
- [OpeningHoursTests.test_specific_services_do_not_inherit_general_health_hours](C:/sahahaha/tests/test_question_intent.py:84)
- [OpeningHoursTests.test_method_query_cannot_be_answered_with_a_location_only](C:/sahahaha/tests/test_question_intent.py:90)
- [OpeningHoursTests.test_source_selection_tries_next_page_when_first_has_no_hours](C:/sahahaha/tests/test_question_intent.py:96)

## test_recycling_category_rules.py (5개)

- [CategoryRuleTests.test_conditional_permission_is_not_service_overview](C:/sahahaha/tests/test_recycling_category_rules.py:13)
  - 문장/변형: 형광등을 봉투에 넣으면 되나요?
  - 문장/변형: 형광등을 봉투에 넣어도 되나요?
- [CategoryRuleTests.test_explicit_category_membership_connects_to_own_rule](C:/sahahaha/tests/test_recycling_category_rules.py:18)
  - 문장/변형: 형광등을 종량제봉투에 넣으면 되나요?
- [CategoryRuleTests.test_adjacent_category_cannot_inherit_rule](C:/sahahaha/tests/test_recycling_category_rules.py:24)
  - 문장/변형: 소형폐가전을 봉투에 넣으면 되나요?
- [CategoryRuleTests.test_two_items_from_different_categories_cannot_share_rule](C:/sahahaha/tests/test_recycling_category_rules.py:27)
  - 문장/변형: 형광등과 소형폐가전을 봉투에 넣으면 되나요?
- [CategoryRuleTests.test_unlisted_item_or_unconfirmed_damage_cannot_inherit_rule](C:/sahahaha/tests/test_recycling_category_rules.py:30)
  - 문장/변형: LED전구를 봉투에 넣으면 되나요?
  - 문장/변형: 깨진 형광등을 봉투에 넣으면 되나요?

## test_reference_answers.py (19개)

- [ReferenceAnswerTests.test_where_to_check_is_navigation_but_clinic_and_course_are_places](C:/sahahaha/tests/test_reference_answers.py:29)
  - 문장/변형: 자전거도로 지도 어디서 볼 수 있어?
  - 문장/변형: 자전거도로 현황도 링크 알려줘
  - 문장/변형: 백신 접종 어디서 해
  - 문장/변형: 소방 안전 교육 어디서 들어
- [ReferenceAnswerTests.test_navigation_has_subject_without_requiring_word_map_in_body](C:/sahahaha/tests/test_reference_answers.py:35)
  - 문장/변형: 자전거도로 지도 어디에서 확인해?
  - 문장/변형: 지도 어디에서 확인해?
- [ReferenceAnswerTests.test_model_cannot_choose_promotion_for_reference_question](C:/sahahaha/tests/test_reference_answers.py:39)
- [ReferenceAnswerTests.test_dated_map_filename_does_not_establish_current_lengths](C:/sahahaha/tests/test_reference_answers.py:52)
- [ReferenceAnswerTests.test_generic_map_question_uses_link_instead_of_promotion](C:/sahahaha/tests/test_reference_answers.py:60)
  - 문장/변형: 자전거도로 알려줘
- [ReferenceAnswerTests.test_source_only_fallback_provides_same_verified_links](C:/sahahaha/tests/test_reference_answers.py:65)
- [ReferenceAnswerTests.test_unrelated_body_or_lookalike_domain_cannot_supply_reference](C:/sahahaha/tests/test_reference_answers.py:71)
- [ReferenceAnswerTests.test_unsafe_attachment_links_are_not_displayed](C:/sahahaha/tests/test_reference_answers.py:76)
- [ReferenceAnswerTests.test_navigation_is_general_and_does_not_require_a_pdf](C:/sahahaha/tests/test_reference_answers.py:82)
  - 문장/변형: 공영주차장 목록 어디에서 확인해?
- [ReferenceAnswerTests.test_quote_retains_source_text_without_standalone_icon_and_escape_noise](C:/sahahaha/tests/test_reference_answers.py:90)
- [ReferenceAnswerTests.test_chunk_metadata_is_hydrated_from_original_with_attachment](C:/sahahaha/tests/test_reference_answers.py:94)
- [ReferenceAnswerTests.test_source_only_map_location_can_answer_without_an_address_field](C:/sahahaha/tests/test_reference_answers.py:105)
  - 문장/변형: 자전거도로 어디야?
- [ReferenceAnswerTests.test_map_navigation_does_not_replace_a_request_for_hours_or_cost](C:/sahahaha/tests/test_reference_answers.py:117)
  - 문장/변형: 자전거도로 이용시간 알려줘
  - 문장/변형: 자전거도로 이용비용 얼마야
- [ReferenceAnswerTests.test_declining_a_link_does_not_override_the_requested_answer_field](C:/sahahaha/tests/test_reference_answers.py:121)
  - 문장/변형: 보건소 운영시간만 알려줘 링크는 필요없어
  - 문장/변형: 여권 링크 말고 비용 얼마야
- [AttachmentPersistenceTests.test_new_attachment_updates_even_with_identical_body](C:/sahahaha/tests/test_reference_answers.py:139)
- [AttachmentPersistenceTests.test_removed_attachment_does_not_remain_as_stale_metadata](C:/sahahaha/tests/test_reference_answers.py:144)
- [AttachmentPersistenceTests.test_identical_body_and_attachment_skip_reindexing](C:/sahahaha/tests/test_reference_answers.py:149)
- [AttachmentPersistenceTests.test_official_refresh_collects_pdf_instead_of_erasing_attachments](C:/sahahaha/tests/test_reference_answers.py:155)
- [AttachmentPersistenceTests.test_import_passes_attachments_to_raw_chunks_and_vector_metadata](C:/sahahaha/tests/test_reference_answers.py:162)

## test_reference_year_roles.py (4개)

- [ReferenceYearRoleTests.test_applicant_event_year_is_not_the_requested_publication_year](C:/sahahaha/tests/test_reference_year_roles.py:22)
- [ReferenceYearRoleTests.test_separate_historical_year_and_statistics_still_need_source_evidence](C:/sahahaha/tests/test_reference_year_roles.py:35)
- [ReferenceYearRoleTests.test_communication_only_and_number_requests_are_different](C:/sahahaha/tests/test_reference_year_roles.py:42)
  - 문장/변형: 마을세무사 상담은 전화만 되는 건가요? 다른 방식도 알려주세요.
  - 문장/변형: 마을세무사 전화번호 알려주세요
  - 문장/변형: 여권 전화만 알려줘
  - 문장/변형: 마을세무사 상담은 전화만 되나요?
- [ReferenceYearRoleTests.test_same_named_program_grant_does_not_become_a_new_service](C:/sahahaha/tests/test_reference_year_roles.py:54)
  - 문장/변형: 자격증 응시료 지원금의 최대 한도가 얼마예요?
  - 문장/변형: 허구축하금 지원금 얼마

## test_request_metrics.py (2개)

- [RequestMetricsTests.test_thread_work_is_attributed_without_question_or_session_text](C:/sahahaha/tests/test_request_metrics.py:9)
- [RequestMetricsTests.test_concurrent_requests_and_failure_keep_separate_measurements](C:/sahahaha/tests/test_request_metrics.py:25)

## test_requested_value_and_condition_scope.py (5개)

- [RequestedValueAndConditionScopeTests.test_colloquial_access_request_wins_over_incidental_free_word](C:/sahahaha/tests/test_requested_value_and_condition_scope.py:13)
  - 문장/변형: 냉장고 무상수거 접수는 어디로 하나요?
- [RequestedValueAndConditionScopeTests.test_requested_percentage_cannot_use_currency_cap](C:/sahahaha/tests/test_requested_value_and_condition_scope.py:22)
  - 문장/변형: 고향사랑기부 답례품 제공 비율의 상한은 몇 퍼센트인가요?
- [RequestedValueAndConditionScopeTests.test_conditional_extension_reads_notice_not_filing_method](C:/sahahaha/tests/test_requested_value_and_condition_scope.py:31)
  - 문장/변형: 정보공개청구 결정이 연장되면 연장 사유도 문서로 알려주나요?
- [RequestedValueAndConditionScopeTests.test_expanded_subservice_retains_explicit_provider_exclusions](C:/sahahaha/tests/test_requested_value_and_condition_scope.py:40)
- [RequestedValueAndConditionScopeTests.test_unrelated_service_cannot_borrow_provider_exclusions](C:/sahahaha/tests/test_requested_value_and_condition_scope.py:48)

## test_response_performance.py (10개)

- [RefreshTests.test_expired_index_serves_consistent_results_while_one_refresh_builds](C:/sahahaha/tests/test_response_performance.py:44)
- [RefreshTests.test_failed_or_empty_rebuild_does_not_mix_old_rows_with_new_scorer](C:/sahahaha/tests/test_response_performance.py:76)
- [RefreshTests.test_page_refresh_retains_snapshot_without_blocking_queries](C:/sahahaha/tests/test_response_performance.py:89)
- [SourceReuseTests.test_known_official_url_skips_global_search_when_complete_original_exists](C:/sahahaha/tests/test_response_performance.py:113)
- [SourceReuseTests.test_freshness_fetch_replaces_a_stale_candidate_body_and_supplies_full_original](C:/sahahaha/tests/test_response_performance.py:123)
- [SourceReuseTests.test_batch_originals_are_reused_after_model_failure_and_missing_rows_fail_closed](C:/sahahaha/tests/test_response_performance.py:140)
- [ModelSelectionTests.test_repeated_selection_is_revalidated_and_hidden_source_changes_invalidate_cache](C:/sahahaha/tests/test_response_performance.py:159)
- [ModelSelectionTests.test_cache_expires_and_has_a_size_limit](C:/sahahaha/tests/test_response_performance.py:174)
- [ModelSelectionTests.test_electronic_services_use_complete_online_instructions_and_exclude_offline_counters](C:/sahahaha/tests/test_response_performance.py:185)
- [ModelSelectionTests.test_online_guide_can_establish_service_kind_without_repeating_online_in_each_sentence](C:/sahahaha/tests/test_response_performance.py:206)

## test_reviewed_field_gate.py (7개)

- [ReviewedFieldGateTests.test_quarantined_field_checks_eligibility_without_extracting_removed_field](C:/sahahaha/tests/test_reviewed_field_gate.py:18)
- [ReviewedFieldGateTests.test_eligibility_only_never_marks_a_source_as_supported](C:/sahahaha/tests/test_reviewed_field_gate.py:24)
- [ReviewedFieldGateTests.test_preflight_without_a_reviewed_url_does_not_fetch_any_original](C:/sahahaha/tests/test_reviewed_field_gate.py:31)
- [ReviewedFieldGateTests.test_conflict_is_explained_with_source_without_calling_model](C:/sahahaha/tests/test_reviewed_field_gate.py:38)
  - 문장/변형: 물리치료실 위치 어디인가요?
- [ReviewedFieldGateTests.test_unblocked_field_and_changed_source_are_not_refused](C:/sahahaha/tests/test_reviewed_field_gate.py:49)
- [ReviewedFieldGateTests.test_mixed_request_continues_to_partial_answer_and_other_service_is_not_warning](C:/sahahaha/tests/test_reviewed_field_gate.py:54)
- [ReviewedFieldGateTests.test_scope_only_is_not_a_medication_dose_candidate](C:/sahahaha/tests/test_reviewed_field_gate.py:58)
  - 문장/변형: 금연약 복용량 하루 몇 정

## test_safety_logic.py (50개)

- [EvidenceGateTests.test_ai_office_lookup_requires_real_ai_work_not_generic_digital_work](C:/sahahaha/tests/test_safety_logic.py:45)
  - 문장/변형: 사하구청 AI담당 부서 알려줘
  - 문장/변형: 인공지능 담당 부서 연락처 알려줘
  - 문장/변형: 양자컴퓨팅 담당 부서 알려줘
  - 문장/변형: 담당 부서 알려줘
  - 문장/변형: airport 담당 부서 알려줘
- [EvidenceGateTests.test_office_lookup_is_not_reranked_into_a_notice_board](C:/sahahaha/tests/test_safety_logic.py:66)
  - 문장/변형: 사하구청 AI담당 부서 알려줘
- [EvidenceGateTests.test_notice_board_columns_are_not_evidence_for_an_office_question](C:/sahahaha/tests/test_safety_logic.py:81)
  - 문장/변형: 사하구청 AI담당 부서 알려줘
  - 문장/변형: 공지사항 게시판 알려줘
- [EvidenceGateTests.test_full_source_board_header_blocks_a_later_retrieval_chunk](C:/sahahaha/tests/test_safety_logic.py:88)
  - 문장/변형: AI 담당 부서 알려줘
- [EvidenceGateTests.test_staff_answer_names_the_verified_office_and_contact_without_raw_page](C:/sahahaha/tests/test_safety_logic.py:101)
  - 문장/변형: 사하구청 AI담당 부서 알려줘
- [EvidenceGateTests.test_new_adult_passport_cannot_quote_emergency_or_official_passport_requirements](C:/sahahaha/tests/test_safety_logic.py:112)
- [EvidenceGateTests.test_kiosk_free_rule_keeps_the_paid_exception](C:/sahahaha/tests/test_safety_logic.py:124)
- [EvidenceGateTests.test_source_answer_preserves_conditions_without_model_synthesis](C:/sahahaha/tests/test_safety_logic.py:133)
- [EvidenceGateTests.test_missing_original_cannot_fall_back_to_unverified_model_answer](C:/sahahaha/tests/test_safety_logic.py:149)
- [EvidenceGateTests.test_year_must_come_from_body_or_report_data_period](C:/sahahaha/tests/test_safety_logic.py:154)
- [EvidenceGateTests.test_official_question_maps_to_url_without_using_draft_answer](C:/sahahaha/tests/test_safety_logic.py:164)
  - 문장/변형: 사하구청은 어디에 있나요?
  - 문장/변형: 사하구청은어디에있나요
- [EvidenceGateTests.test_exact_rows_prevent_mixing_birth_and_health_fees](C:/sahahaha/tests/test_safety_logic.py:172)
- [EvidenceGateTests.test_birth_benefit_programs_are_split_before_embedding](C:/sahahaha/tests/test_safety_logic.py:187)
- [EvidenceGateTests.test_lookalike_domain_is_not_official](C:/sahahaha/tests/test_safety_logic.py:203)
- [EvidenceGateTests.test_historical_report_cannot_answer_current_or_2026_counts](C:/sahahaha/tests/test_safety_logic.py:207)
  - 문장/변형: 현재 정보공개청구는 몇 건?
- [EvidenceGateTests.test_numerical_claim_must_exist_in_retrieved_context](C:/sahahaha/tests/test_safety_logic.py:215)
- [EvidenceGateTests.test_stale_web_page_is_not_used_for_current_fee](C:/sahahaha/tests/test_safety_logic.py:221)
- [EvidenceGateTests.test_report_context_includes_period_without_local_file_link](C:/sahahaha/tests/test_safety_logic.py:239)
- [EvidenceGateTests.test_out_of_domain_is_blocked_even_with_high_vector_similarity](C:/sahahaha/tests/test_safety_logic.py:250)
- [EvidenceGateTests.test_official_lexical_evidence_is_accepted](C:/sahahaha/tests/test_safety_logic.py:256)
- [EvidenceGateTests.test_admin_intent_alone_cannot_establish_answer_evidence](C:/sahahaha/tests/test_safety_logic.py:262)
- [EvidenceGateTests.test_non_official_source_is_never_accepted](C:/sahahaha/tests/test_safety_logic.py:268)
- [EvidenceGateTests.test_non_official_high_score_cannot_lend_support_to_official_document](C:/sahahaha/tests/test_safety_logic.py:273)
- [EvidenceGateTests.test_grounded_selection_excludes_unmatched_documents](C:/sahahaha/tests/test_safety_logic.py:285)
- [EvidenceGateTests.test_admin_intent_still_requires_actual_service_evidence](C:/sahahaha/tests/test_safety_logic.py:294)
- [ConversationUxTests.test_obvious_financial_prediction_is_blocked_before_retrieval](C:/sahahaha/tests/test_safety_logic.py:302)
  - 문장/변형: 사하구 지방세 납부 방법 알려줘
- [ConversationUxTests.test_vague_request_produces_clarification_and_choices](C:/sahahaha/tests/test_safety_logic.py:306)
  - 문장/변형: 지원받고 싶어요
- [ConversationUxTests.test_specific_request_does_not_trigger_clarification](C:/sahahaha/tests/test_safety_logic.py:311)
  - 문장/변형: 장애인 활동지원 신청 방법 알려줘
- [ConversationUxTests.test_bed_fee_requires_size_clarification](C:/sahahaha/tests/test_safety_logic.py:314)
  - 문장/변형: 침대 배출 수수료가 얼마야?
- [ConversationUxTests.test_bed_fee_with_specific_size_does_not_clarify](C:/sahahaha/tests/test_safety_logic.py:320)
  - 문장/변형: 일반침대 2인용 수수료가 얼마야?
- [ConversationUxTests.test_follow_up_questions_are_deduplicated_and_limited](C:/sahahaha/tests/test_safety_logic.py:323)
  - 문장/변형: 복지 지원 알려줘
- [ConversationUxTests.test_follow_up_search_keeps_recent_user_context](C:/sahahaha/tests/test_safety_logic.py:329)
  - 문장/변형: 대형 폐기물 배출 방법 알려줘
  - 문장/변형: 종류를 알려주세요
- [ConversationUxTests.test_new_topic_does_not_inherit_previous_question](C:/sahahaha/tests/test_safety_logic.py:338)
  - 문장/변형: 2026년 출산지원금은 얼마인가요?
  - 문장/변형: 정보공개청구 통계를 알려줘
- [ConversationUxTests.test_new_complete_question_drops_previous_topic](C:/sahahaha/tests/test_safety_logic.py:343)
  - 문장/변형: 기초생활수급자 민원 수수료 면제 알려줘
- [ConversationUxTests.test_vague_service_request_preserves_one_scope_question](C:/sahahaha/tests/test_safety_logic.py:351)
  - 문장/변형: 지원받고 싶어요
- [PrivacyTests.test_sensitive_input_is_detected_before_storage](C:/sahahaha/tests/test_safety_logic.py:356)
- [PrivacyTests.test_sensitive_output_is_masked](C:/sahahaha/tests/test_safety_logic.py:360)
- [MetadataFallbackTests.test_keywords_are_generated_without_llm](C:/sahahaha/tests/test_safety_logic.py:366)
- [MetadataFallbackTests.test_hallucinated_department_is_removed](C:/sahahaha/tests/test_safety_logic.py:371)
- [MetadataFallbackTests.test_page_department_hint_overrides_llm_guess](C:/sahahaha/tests/test_safety_logic.py:385)
- [MetadataFallbackTests.test_explicit_department_is_extracted_from_page_footer](C:/sahahaha/tests/test_safety_logic.py:399)
- [IncrementalCrawlerTests.test_robots_denied_known_page_is_not_reported_as_deleted](C:/sahahaha/tests/test_safety_logic.py:406)
- [IncrementalCrawlerTests.test_urls_seen_in_previous_menu_are_not_fetched_again](C:/sahahaha/tests/test_safety_logic.py:416)
- [IncrementalCrawlerTests.test_attachment_is_source_metadata_not_a_page_link](C:/sahahaha/tests/test_safety_logic.py:429)
- [IncrementalCrawlerTests.test_lookalike_domain_is_rejected](C:/sahahaha/tests/test_safety_logic.py:442)
- [IncrementalCrawlerTests.test_new_links_stay_in_their_administrative_menu](C:/sahahaha/tests/test_safety_logic.py:450)
- [HybridRankingTests.test_exact_bm25_match_can_beat_unrelated_vector_candidate](C:/sahahaha/tests/test_safety_logic.py:460)
- [HybridRankingTests.test_complete_original_uses_fast_path_without_vector_call](C:/sahahaha/tests/test_safety_logic.py:484)
- [HybridRankingTests.test_fee_waiver_question_is_not_treated_as_staff_lookup](C:/sahahaha/tests/test_safety_logic.py:514)
- [HybridRankingTests.test_unrelated_staff_document_is_not_used_as_source](C:/sahahaha/tests/test_safety_logic.py:520)

## test_semantic_ranker.py (32개)

- [SemanticRankerTests.test_warmup_runs_one_bounded_batch_without_caching_synthetic_scores](C:/sahahaha/tests/test_semantic_ranker.py:25)
- [SemanticRankerTests.test_failed_precalculation_does_not_remove_loaded_model](C:/sahahaha/tests/test_semantic_ranker.py:37)
- [SemanticRankerTests.test_synonym_binding_can_establish_topic_but_not_missing_field](C:/sahahaha/tests/test_semantic_ranker.py:46)
  - 문장/변형: 담배를 끊고 싶은데 어디서 상담해요?
- [SemanticRankerTests.test_changed_question_or_source_invalidates_binding](C:/sahahaha/tests/test_semantic_ranker.py:54)
  - 문장/변형: 담배를 끊고 싶어요
  - 문장/변형: 술을 끊고 싶어요
- [SemanticRankerTests.test_low_logit_or_small_margin_does_not_bypass_topic](C:/sahahaha/tests/test_semantic_ranker.py:63)
- [SemanticRankerTests.test_official_and_district_guards_remain_with_semantic_binding](C:/sahahaha/tests/test_semantic_ranker.py:68)
- [SemanticRankerTests.test_explicit_service_contradiction_is_not_overridden](C:/sahahaha/tests/test_semantic_ranker.py:75)
  - 문장/변형: 폐렴구균 접종 장소 알려줘
- [SemanticRankerTests.test_missing_local_model_preserves_existing_candidates](C:/sahahaha/tests/test_semantic_ranker.py:80)
- [SemanticRankerTests.test_passage_never_borrows_changed_vector_chunk](C:/sahahaha/tests/test_semantic_ranker.py:87)
- [SemanticRankerTests.test_packet_keywords_cannot_leak_to_another_source](C:/sahahaha/tests/test_semantic_ranker.py:92)
  - 문장/변형: 담배 끊는 상담 내용 알려줘
- [SemanticRankerTests.test_field_heading_labels_value_without_changing_owner](C:/sahahaha/tests/test_semantic_ranker.py:106)
- [SemanticRankerTests.test_weekday_reservation_period_is_a_schedule](C:/sahahaha/tests/test_semantic_ranker.py:111)
- [SemanticRankerTests.test_generic_title_requires_an_opening_fact_about_requested_subject](C:/sahahaha/tests/test_semantic_ranker.py:114)
- [SemanticRankerTests.test_field_heading_cannot_narrow_a_different_requested_field](C:/sahahaha/tests/test_semantic_ranker.py:121)
- [SemanticRankerTests.test_official_example_markers_do_not_drop_the_exclusion_row](C:/sahahaha/tests/test_semantic_ranker.py:126)
- [SemanticRankerTests.test_waste_pickup_is_not_a_document_request](C:/sahahaha/tests/test_semantic_ranker.py:130)
- [SemanticRankerTests.test_general_clinic_audience_is_not_drug_dosage_evidence](C:/sahahaha/tests/test_semantic_ranker.py:135)
  - 문장/변형: 금연클리닉에서 어떤 약을 처방하는지 이름과 복용량 알려줘
- [SemanticSafetyTests.test_known_subject_filters_bus_before_bicycle_reranking](C:/sahahaha/tests/test_semantic_ranker.py:142)
  - 문장/변형: 자전거 지도 어디서 확인해?
- [SemanticSafetyTests.test_bicycle_mention_in_parking_rule_is_not_a_bicycle_map](C:/sahahaha/tests/test_semantic_ranker.py:148)
  - 문장/변형: 자전거길 노선 지도 어디에서 볼 수 있어요?
- [SemanticSafetyTests.test_reference_field_words_do_not_hide_bicycle_topic](C:/sahahaha/tests/test_semantic_ranker.py:153)
  - 문장/변형: 자전거길 공식 노선 지도는 어디에서 볼 수 있나요?
- [SemanticSafetyTests.test_general_health_hours_reject_infant_provider_list](C:/sahahaha/tests/test_semantic_ranker.py:160)
  - 문장/변형: 보건소 진료시간이랑 주소 알려줘
- [SemanticSafetyTests.test_colloquial_age_reply_keeps_passport_and_parent_role](C:/sahahaha/tests/test_semantic_ranker.py:165)
  - 문장/변형: 고등학생 여권 준비물 알려줘
- [SemanticSafetyTests.test_fee_connective_is_not_a_location_request](C:/sahahaha/tests/test_semantic_ranker.py:175)
- [SemanticSafetyTests.test_semantic_topic_remains_bicycle_not_bus](C:/sahahaha/tests/test_semantic_ranker.py:179)
  - 문장/변형: 자전거 도로 지도 볼 수 있는 공식 페이지 알려줘
- [SemanticSafetyTests.test_incidental_facility_mention_cannot_replace_requested_owner](C:/sahahaha/tests/test_semantic_ranker.py:186)
  - 문장/변형: 마을건강센터 건강 상담 알려줘
- [SemanticSafetyTests.test_configured_timeout_is_passed_to_ollama_http_client](C:/sahahaha/tests/test_semantic_ranker.py:191)
- [SemanticSafetyTests.test_pdf_carried_over_clause_is_not_an_answer](C:/sahahaha/tests/test_semantic_ranker.py:199)
- [SemanticSafetyTests.test_semantics_cannot_replace_nonexistent_named_grant](C:/sahahaha/tests/test_semantic_ranker.py:203)
  - 문장/변형: 사하구청 우주여행 지원금 300만원을 신청하려면 어떻게 하나요?
- [SemanticSafetyTests.test_named_village_center_is_not_dementia_center](C:/sahahaha/tests/test_semantic_ranker.py:208)
- [SemanticSafetyTests.test_shared_document_question_does_not_select_maternity_aid](C:/sahahaha/tests/test_semantic_ranker.py:213)
- [SemanticSafetyTests.test_explicit_reservation_need_and_natural_fee_questions_have_fields](C:/sahahaha/tests/test_semantic_ranker.py:219)
- [SemanticSafetyTests.test_compound_fallback_cannot_silently_omit_requested_cost](C:/sahahaha/tests/test_semantic_ranker.py:224)
  - 문장/변형: 응시료 지원은 얼마나 주고 어떻게 신청해요?

## test_source_requirement_groups.py (12개)

- [RequirementGroupTests.test_named_member_institution_can_find_its_actual_program](C:/sahahaha/tests/test_source_requirement_groups.py:13)
- [RequirementGroupTests.test_membership_cannot_establish_another_institution_or_location](C:/sahahaha/tests/test_source_requirement_groups.py:19)
  - 문장/변형: 다대도서관 희망도서 신청 한도 알려줘
  - 문장/변형: 작은도서관 주소 알려줘
- [RequirementGroupTests.test_sibling_program_membership_cannot_establish_requested_owner](C:/sahahaha/tests/test_source_requirement_groups.py:24)
- [RequirementGroupTests.test_heir_documents_keep_common_id_and_not_proxy_papers](C:/sahahaha/tests/test_source_requirement_groups.py:28)
- [RequirementGroupTests.test_common_id_closure_is_shared_with_model_and_fallback_readers](C:/sahahaha/tests/test_source_requirement_groups.py:34)
- [RequirementGroupTests.test_all_declared_criteria_are_kept_with_age_income_and_exceptions](C:/sahahaha/tests/test_source_requirement_groups.py:41)
  - 문장/변형: 영양플러스는 영유아도 대상인가요? 소득 기준도 함께 알려주세요.
- [RequirementGroupTests.test_incomplete_numbered_group_cannot_be_reported_as_all_requirements](C:/sahahaha/tests/test_source_requirement_groups.py:48)
- [RequirementGroupTests.test_criteria_group_does_not_invent_unstated_nationality](C:/sahahaha/tests/test_source_requirement_groups.py:52)
  - 문장/변형: 외국인 영유아도 영양플러스 신청 대상인가요?
- [RequirementGroupTests.test_fallback_does_not_present_general_criteria_as_nationality_proof](C:/sahahaha/tests/test_source_requirement_groups.py:57)
  - 문장/변형: 외국인 영유아도 영양플러스 신청 대상인가요?
- [RequirementGroupTests.test_explicit_foreign_applicant_rule_differs_from_household_count](C:/sahahaha/tests/test_source_requirement_groups.py:63)
  - 문장/변형: 외국인 영유아도 신청 대상인가요?
- [RequirementGroupTests.test_duties_request_selects_work_not_just_definition](C:/sahahaha/tests/test_source_requirement_groups.py:68)
  - 문장/변형: 부산 사하구 납세자보호관은 어떤 일을 하는지 알려주세요.
- [RequirementGroupTests.test_explicit_action_subject_is_not_asked_again](C:/sahahaha/tests/test_source_requirement_groups.py:73)

## test_specific_source_fields.py (7개)

- [SpecificSourceFieldsTests.test_first_issue_marker_is_lifecycle_not_required_literal_in_original](C:/sahahaha/tests/test_specific_source_fields.py:17)
  - 문장/변형: 주민등록증 신규 발급이 처음인데 신청부터 받기까지 어떻게 진행돼요?
- [SpecificSourceFieldsTests.test_damaged_item_cannot_use_general_free_membership_table](C:/sahahaha/tests/test_specific_source_fields.py:25)
- [SpecificSourceFieldsTests.test_embedded_applicant_age_in_complete_cell](C:/sahahaha/tests/test_specific_source_fields.py:34)
  - 문장/변형: 해외여행클리닉 말라리아 처방전은 만 몇 세부터 받을 수 있나요?
- [SpecificSourceFieldsTests.test_phone_inside_land_notice_is_not_calendar_month](C:/sahahaha/tests/test_specific_source_fields.py:42)
  - 문장/변형: 개별공시지가 이의신청은 몇 월에 해요?
- [SpecificSourceFieldsTests.test_definition_has_meaning_not_only_operating_history](C:/sahahaha/tests/test_specific_source_fields.py:51)
- [SpecificSourceFieldsTests.test_information_education_does_not_borrow_lifelong_program_fee](C:/sahahaha/tests/test_specific_source_fields.py:56)
  - 문장/변형: 사하구 정보화교육은 수강료가 얼마인가요?
- [SpecificSourceFieldsTests.test_conflicting_clinic_floor_is_quarantined_until_source_changes](C:/sahahaha/tests/test_specific_source_fields.py:67)

## test_vaccine_locations.py (17개)

- [VaccinePlaceTests.test_original_unspecified_vaccine_prompts_one_short_question_without_search](C:/sahahaha/tests/test_vaccine_locations.py:49)
  - 문장/변형: 백신 접종 하는곳 알려줘
- [VaccinePlaceTests.test_colloquial_generic_location_questions_also_ask_the_type](C:/sahahaha/tests/test_vaccine_locations.py:65)
  - 문장/변형: 예방접종 어디서 해?
  - 문장/변형: 백신 맞는 곳 알려줘
  - 문장/변형: 백신 접종장소 알려줘
- [VaccinePlaceTests.test_short_type_reply_keeps_place_goal_and_new_topic_stays_separate](C:/sahahaha/tests/test_vaccine_locations.py:69)
  - 문장/변형: 백신 접종 하는곳 알려줘
  - 문장/변형: B형간염 검사 비용 알려줘
- [VaccinePlaceTests.test_followup_cost_keeps_vaccine_type_but_replaces_previous_place_goal](C:/sahahaha/tests/test_vaccine_locations.py:78)
  - 문장/변형: 독감 접종 장소 알려줘
- [VaccinePlaceTests.test_precise_type_does_not_trigger_repeated_type_question](C:/sahahaha/tests/test_vaccine_locations.py:85)
  - 문장/변형: 독감 어디서 맞아?
- [VaccinePlaceTests.test_location_match_is_not_incidental_hospital_mention](C:/sahahaha/tests/test_vaccine_locations.py:90)
- [VaccinePlaceTests.test_colonless_place_row_is_paired_but_unrelated_cells_are_not](C:/sahahaha/tests/test_vaccine_locations.py:97)
- [VaccinePlaceTests.test_location_query_cannot_be_answered_with_eligibility_exception](C:/sahahaha/tests/test_vaccine_locations.py:103)
- [VaccinePlaceTests.test_pneumococcal_place_keeps_age_program_scope_and_no_health_center_injection](C:/sahahaha/tests/test_vaccine_locations.py:109)
- [VaccinePlaceTests.test_influenza_place_keeps_geographic_restriction_and_annual_provider_notice](C:/sahahaha/tests/test_vaccine_locations.py:118)
  - 문장/변형: 독감 어디서 맞아?
- [VaccinePlaceTests.test_hepatitis_place_uses_first_table_not_another_vaccine_program](C:/sahahaha/tests/test_vaccine_locations.py:127)
- [VaccinePlaceTests.test_incomplete_structure_does_not_fall_back_to_wrong_program](C:/sahahaha/tests/test_vaccine_locations.py:133)
- [VaccinePlaceTests.test_other_products_or_populations_do_not_inherit_senior_ppsv23_place](C:/sahahaha/tests/test_vaccine_locations.py:140)
- [VaccinePlaceTests.test_named_vaccine_selects_official_url_without_routing_unrelated_services](C:/sahahaha/tests/test_vaccine_locations.py:145)
- [VaccinePlaceTests.test_general_health_center_location_uses_directions_not_a_program_room](C:/sahahaha/tests/test_vaccine_locations.py:152)
  - 문장/변형: 보건소 위치 알려줘
  - 문장/변형: 보건소 어디야?
- [VaccinePlaceTests.test_location_and_generic_vaccine_words_do_not_hide_specific_type](C:/sahahaha/tests/test_vaccine_locations.py:158)
  - 문장/변형: 백신 접종 하는곳 알려줘 독감
  - 문장/변형: 독감 어디서 맞아?
  - 문장/변형: 보건소 위치 알려줘
  - 문장/변형: 구민문화회관 위치 알려줘
- [VaccinePlaceTests.test_source_selection_skips_history_only_page_and_uses_actual_place](C:/sahahaha/tests/test_vaccine_locations.py:166)

## test_worker_recovery.py (11개)

- [WorkerRecoveryTests.test_restart_and_long_sleep_recover_successfully_without_repeating_fresh_jobs](C:/sahahaha/tests/test_worker_recovery.py:21)
- [WorkerRecoveryTests.test_failure_keeps_last_success_and_backs_off_while_other_jobs_continue](C:/sahahaha/tests/test_worker_recovery.py:33)
- [WorkerRecoveryTests.test_partial_refresh_is_not_reported_as_success](C:/sahahaha/tests/test_worker_recovery.py:47)
- [WorkerRecoveryTests.test_second_worker_cannot_run_same_job_concurrently](C:/sahahaha/tests/test_worker_recovery.py:54)
- [WorkerRecoveryTests.test_interrupted_running_state_or_future_success_is_retried](C:/sahahaha/tests/test_worker_recovery.py:63)
- [WorkerRecoveryTests.test_corrupt_state_is_recovered_and_write_is_atomic](C:/sahahaha/tests/test_worker_recovery.py:69)
- [WorkerRecoveryTests.test_forced_cron_failure_retries_even_after_a_recent_success](C:/sahahaha/tests/test_worker_recovery.py:76)
- [SnapshotSafetyTests.test_changed_wording_cannot_bypass_the_dynamic_source_age_limit](C:/sahahaha/tests/test_worker_recovery.py:88)
  - 문장/변형: 희망도서 몇 권 신청할 수 있어?
- [SnapshotSafetyTests.test_missing_stale_and_future_staff_snapshots_never_start_a_chat_crawl](C:/sahahaha/tests/test_worker_recovery.py:95)
- [SnapshotSafetyTests.test_future_timestamp_does_not_verify_a_fact_or_contact](C:/sahahaha/tests/test_worker_recovery.py:107)
- [SnapshotSafetyTests.test_staff_crawl_timeout_preserves_the_saved_snapshot](C:/sahahaha/tests/test_worker_recovery.py:114)
