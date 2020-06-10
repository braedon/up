% rebase('base.tpl', title='up? - Page Not Found')
<main>
  <span class="spacer"></span>
  <div class="content">
    <h1>up?</h1>
    <div class="section">
      % if error.body and not error.body.startswith('Not found: '):
      <p>{{error.body}}</p>
      % else:
      <p>Oops, that page doesn't exist</p>
      % end
    </div>
  </div>
  <span class="spacer"></span>
  <div class="linkRow">
    <a href="/">Got a link?</a>
  </div>
</main>
