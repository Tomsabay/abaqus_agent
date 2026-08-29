"""The truth layer that reads the .inp Abaqus just wrote.

Everything here runs INSIDE the Abaqus kernel (Python 2.7), spliced into the
generated script by runner/kernel_runtime.py. It sits in its own file because
it is one topic -- what the deck actually says, as opposed to what the model
was asked for -- and because kernel_runtime.py is already over the size the
module gate allows, so the next helper had nowhere to go.

The text is byte-identical to what used to live there. Moving it must not
change a single generated deck; tests/test_frozen_model_sections.py holds that.
"""

from __future__ import annotations

_H_DECK = '''\
def _expect_cload(a, inp_path, stated):
    \"\"\"Every *Cload the input file carries, and how many nodes it lands on.

    Read out of the file Abaqus just wrote, rather than guessed from the shape
    of the selector. A concentrated force and a moment both write *Cload, and
    so will whatever the next release adds; nothing here has to know which
    calls those are.

    Two measurements make this the only place the check can live.

    The magnitude is PER NODE. On a 10x10x100 cantilever, cf2=-100 on a set of
    the four tip corners: total reaction 400 N, tip -0.7584553 mm. The same
    call at cf2=-25 on the same four nodes: 100 N, -0.1896138, which is
    P L^3 / (3 E I) to 0.45%. Both COMPLETE with no warning.

    And CAE's own guard does not run here. Submitting a concentrated force on a
    face-based set from CAE is refused outright -- "contains invalid geometry
    or mesh components for the load type", and no input file is written. But
    this deck calls writeInput(consistencyChecking=OFF), so that check is
    skipped and the card comes out as `*Cload / TIP, 2, -100.` against an Nset
    of four nodes. The solver then applies 400 N and reports success.

    The input file is removed before this raises: leaving it behind would let
    a caller that tests for its existence treat a refused build as a good one.
    \"\"\"
    try:
        handle = open(inp_path)
        try:
            lines = handle.read().splitlines()
        finally:
            handle.close()
    except Exception:
        _sel_log('CLOAD_UNREADABLE: %s' % inp_path)
        return

    targets = []
    index = 0
    while index < len(lines):
        if lines[index].strip().lower().startswith('*cload'):
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith('*'):
                body = lines[index].strip()
                if body:
                    targets.append(body.split(',')[0].strip())
                index += 1
            continue
        index += 1

    problems = []
    for name in targets:
        try:
            count = _load_points(a, name)
        except Exception:
            # A bare node number, or a set this side cannot see. Reported
            # rather than guessed at.
            _sel_log('CLOAD_UNKNOWN_SET: %s' % name)
            continue
        if count <= 1:
            _sel_log('CLOAD_OK: %s lands on %d node(s)' % (name, count))
            continue
        want = stated.get(name)
        if want is None:
            problems.append(
                '%s lands on %d node(s) and the spec never said so'
                % (name, count))
        elif want != count:
            problems.append('%s lands on %d node(s), the spec says %d'
                            % (name, count, want))
        else:
            _sel_log('CLOAD_OK: %s lands on %d node(s), as stated, so the '
                     'total is %d x the magnitude written' % (name, count, count))
    if problems:
        try:
            os.remove(inp_path)
        except Exception:
            pass
        _expect_fail(
            'CLOAD_PER_NODE: %s. A concentrated load is written PER NODE, so '
            'the magnitude in the spec is not the load applied -- measured on '
            'Abaqus 2021, cf2=-100 on four corners totals 400 N and the job '
            'completes without a warning. To load a whole FACE, couple it to a '
            'reference point and put the load on the point (call: Coupling, '
            'then region: {named_set: RP_NAME}): one node, so the magnitude is '
            'the load. For a set of named nodes instead, state the count with '
            '`expect: {points: N}` and divide the magnitude yourself.'
            % '; '.join(problems))


def _expect_keywords(inp_path, wanted):
    \"\"\"Every line a keywordBlock insert asked for is in the file that was written.

    `m.keywordBlock` is the escape hatch: a card this dialect has no name for,
    typed as text and spliced into the deck. Everything else in the deck is
    checked by asking the model what it contains; a keyword block cannot be,
    because the model has no opinion about text. So the only available check is
    to read the input file back and look for it.

    What was measured on Abaqus 2021 (artifacts/probe_keyword_block), and it
    is NOT what this was written expecting. `position` names a block in
    keywordBlock.sieBlocks and the text goes AFTER that block, so what the
    integer lands on decides everything:

      insert(21), after *Elastic    card in the deck, no conflict block,
                                    datacheck 0 errors -- the escape hatch
                                    working, a *Damping card CAE has no field
                                    for reaching the solver
      insert(3), inside *Element    card in the deck, KEYWORD_OK logged, and
                                    the deck is wrapped in *Conflicts: 4 FATAL
                                    ERRORS, EXECUTION IS TERMINATED
      insert(1), after *Part        card in the deck, no conflict block, 1
                                    fatal error -- *Damping is not legal there
      insert(100000)                IndexError, build aborts
      insert(-5)                    IndexError, build aborts
      no synchVersions first        card in the deck -- not required on this
                                    model, contrary to what was assumed
      synchVersions after insert    card still in the deck -- a later
                                    synchronise did not discard the edit

    So the missing-card case this was written for has never been observed, and
    a worse one has: the card arrives, this check says KEYWORD_OK, and the deck
    is unreadable. That is what the *Conflicts test below is for, and it is the
    verified counterexample the read-back itself still lacks. The read-back is
    kept because it costs nothing on top of a file read that now has to happen
    anyway.

    What neither test can see is insert(1): conflict-free, in the deck, and
    illegal where it landed. Only the input file processor knows that, and it
    says so loudly when the job runs -- so it is left to the job rather than
    guessed at here.

    Compared with whitespace squeezed and case folded, because Abaqus rewrites
    a card's spacing and capitalisation freely -- a literal comparison would
    refuse decks that carry exactly what was asked for.

    The input file is removed before this raises, for the same reason
    _expect_cload removes it: a caller that tests for its existence must not
    read a refused build as a good one.
    \"\"\"
    if not wanted:
        return
    try:
        handle = open(inp_path)
        try:
            deck = handle.read()
        finally:
            handle.close()
    except Exception:
        _sel_log('KEYWORDS_UNREADABLE: %s' % inp_path)
        return

    squeezed = ' '.join(deck.split()).upper()
    missing = []
    for where, text in wanted:
        needle = ' '.join(str(text).split()).upper()
        if needle and needle not in squeezed:
            missing.append('%s asked for %r' % (where, text))
        else:
            _sel_log('KEYWORD_OK: %s is in the deck' % where)
    if missing:
        try:
            os.remove(inp_path)
        except Exception:
            pass
        _expect_fail(
            'KEYWORD_NOT_WRITTEN: %s, and the written input file does not '
            'contain it. The call itself did not raise, so the card was '
            'accepted by the block and then did not reach the deck -- the job '
            'would have run without it. Measured on Abaqus 2021, an out-of-'
            'range position raises IndexError instead, so this is not that: '
            'look at what the block held when the insert ran.'
            % '; '.join(missing))

    if '*CONFLICTS' in squeezed:
        try:
            os.remove(inp_path)
        except Exception:
            pass
        _expect_fail(
            'KEYWORD_CONFLICT_BLOCK: the card is in the deck and the deck '
            'cannot be read. CAE wrapped the edit in a *Conflicts block, which '
            'is not an analysis keyword -- Abaqus/Standard reports it as a '
            'fatal input error and stops before the first increment. Measured '
            'on Abaqus 2021 with the same card and the same spec: insert after '
            'block 21 (the end of *Elastic) datachecks with 0 errors, insert '
            'after block 3 (inside the generated *Element table) produces this '
            'block and 4 FATAL ERRORS. A position must name the end of a '
            'block, not a line inside one; enumerate keywordBlock.sieBlocks to '
            'see where the boundaries are.')


def _expect_steps(m, wanted):
    \"\"\"The analysis runs the steps in the order the spec wrote them.

    Not a formality. Measured on Abaqus 2021: two StaticSteps both declaring
    `previous='Initial'` are BOTH accepted, and the second one is inserted
    BEFORE the first -- m.steps comes out ('Initial', 'Two', 'One') and the ODB
    agrees. The job completes. A preload-then-load analysis written in the
    obvious order runs backwards and nothing says so.
    \"\"\"
    got = [name for name in m.steps.keys() if name != 'Initial']
    if got != list(wanted):
        _expect_fail(
            'STEP_ORDER: the analysis runs %s, the spec wrote %s. Abaqus '
            'inserts a step after the one named in `previous:`, so two steps '
            'that both follow Initial come out in the reverse of the order '
            'they were written -- measured, and the job still completes.'
            % (' -> '.join(got) or 'nothing', ' -> '.join(wanted)))
    _sel_log('STEP_ORDER_OK: %s' % (' -> '.join(got) or 'nothing'))


'''
