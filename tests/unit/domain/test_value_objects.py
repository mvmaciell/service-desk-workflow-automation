from src.megahub_monitor.domain.value_objects import SubscriptionFilter, TicketId


class TestTicketId:
    def test_equality(self):
        a = TicketId(number="100", source_id="s1")
        b = TicketId(number="100", source_id="s1")
        assert a == b

    def test_inequality(self):
        a = TicketId(number="100", source_id="s1")
        b = TicketId(number="101", source_id="s1")
        assert a != b

    def test_immutable(self):
        tid = TicketId(number="100", source_id="s1")
        assert hash(tid) is not None


class TestSubscriptionFilter:
    def test_empty_filter_matches_everything(self, make_ticket):
        f = SubscriptionFilter()
        ticket = make_ticket()
        assert f.matches(ticket) is True

    def test_matches_ticket_type(self, make_ticket):
        f = SubscriptionFilter(ticket_types=frozenset({"incidente"}))
        assert f.matches(make_ticket(ticket_type="Incidente")) is True
        assert f.matches(make_ticket(ticket_type="Solicitacao")) is False

    def test_matches_priority(self, make_ticket):
        f = SubscriptionFilter(priorities=frozenset({"alta"}))
        assert f.matches(make_ticket(priority="Alta")) is True
        assert f.matches(make_ticket(priority="Baixa")) is False

    def test_matches_company(self, make_ticket):
        f = SubscriptionFilter(companies=frozenset({"empresa abc"}))
        assert f.matches(make_ticket(company="Empresa ABC")) is True
        assert f.matches(make_ticket(company="Empresa XYZ")) is False

    def test_matches_consultant(self, make_ticket):
        f = SubscriptionFilter(consultants=frozenset({"marcus vinicius"}))
        assert f.matches(make_ticket(consultant="Marcus Vinicius")) is True
        assert f.matches(make_ticket(consultant="Outro Nome")) is False

    def test_matches_front(self, make_ticket):
        f = SubscriptionFilter(fronts=frozenset({"abap"}))
        assert f.matches(make_ticket(front="ABAP")) is True
        assert f.matches(make_ticket(front="Fiori")) is False

    def test_accent_insensitive(self, make_ticket):
        f = SubscriptionFilter(companies=frozenset({"solucao"}))
        assert f.matches(make_ticket(company="Solução")) is True

    def test_multiple_filters_all_must_match(self, make_ticket):
        f = SubscriptionFilter(
            ticket_types=frozenset({"incidente"}),
            priorities=frozenset({"alta"}),
        )
        assert f.matches(make_ticket(ticket_type="Incidente", priority="Alta")) is True
        assert f.matches(make_ticket(ticket_type="Incidente", priority="Baixa")) is False
        assert f.matches(make_ticket(ticket_type="Solicitacao", priority="Alta")) is False

    def test_multiple_values_in_filter_acts_as_or(self, make_ticket):
        f = SubscriptionFilter(priorities=frozenset({"alta", "critica"}))
        assert f.matches(make_ticket(priority="Alta")) is True
        assert f.matches(make_ticket(priority="Critica")) is True
        assert f.matches(make_ticket(priority="Baixa")) is False

    def test_empty_ticket_field_does_not_match_non_empty_filter(self, make_ticket):
        f = SubscriptionFilter(consultants=frozenset({"marcus"}))
        assert f.matches(make_ticket(consultant="")) is False

    def test_immutable(self):
        f = SubscriptionFilter(ticket_types=frozenset({"incidente"}))
        assert hash(f) is not None
