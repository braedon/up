% rebase('base.tpl', title='up? - Error')
<div id="content">
  <h1>up?</h1>
  <div class="message">
    % if error.body and error.status_code < 500:
    {{error.body}}
    % else:
    Oops, something went wrong
    % end
  </div>
  <div class="message">
    <a href="/">Got a link?</a>
  </div>
</div>
