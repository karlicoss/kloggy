-- Pandoc's GitHub markdown output drops explicit heading ids (e.g. `### Z3: Some title {#z3}`),
--   since GitHub makes up heading anchors from their text instead.
-- So links like [Z3](#z3) would be broken on GitHub.
-- This keeps such ids as explicit anchors in the heading: `### <a id="z3"></a>Z3: Some title`.

-- anchor GitHub generates for a heading (github-slugger), ASCII only
local function github_anchor(text)
  local res = text:lower():gsub('[^%w_ %-]', ''):gsub(' ', '-')
  return res
end

function Header(header)
  if not quarto.doc.is_format('gfm') then
    return nil
  end
  if header.identifier == '' or header.identifier == github_anchor(pandoc.utils.stringify(header.content)) then
    -- GitHub's own anchor works
    return nil
  end
  header.content:insert(1, pandoc.RawInline('html', ('<a id="%s"></a>'):format(header.identifier)))
  return header
end
