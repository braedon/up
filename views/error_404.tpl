% rebase('base.tpl', title='up? - Page Not Found')
<div id="content">
  <h1>up?</h1>
  <div class="message">
    % if error.body and not error.body.startswith('Not found: '):
    {{error.body}}
    % else:
    Oops, that page doesn't exist
    % end
  </div>
  <div class="message">
    <a href="/">Got a link?</a>
  </div>
</div>
