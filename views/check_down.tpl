% rebase('base.tpl', title='up? - Link Down')
<main>
  <div class="header">
    <span class="spacer"></span>
    <a class="buttonLike" href="/logout">Log Out</a>
  </div>
  <span class="spacer"></span>
  <div class="content limitWidth">
    <h1>down!</h1>
    % if defined('alert') and alert:
    <div class="section alert">
      % if alert == 'insufficient-scope':
      <p>Offline Access and Contact permissions are required for notifications</p>
      % end
    </div>
    % end
    <div class="section">
      <p>
        That <a href="{{url}}" target="_blank" rel="noopener noreferrer">link</a>
        does seem to be down.
      </p>
      <p>Should we notify you via {{oidc_name}} when it's back up?</p>
    </div>
    <%
    from urllib.parse import urlencode
    qs_dict = {
      'url': url,
    }
    qs = urlencode(qs_dict)
    %>
    <form class="section" action="/link?{{qs}}" method="POST">
      <input type="hidden" name="csrf" value="{{csrf}}">
      <button class="mainButton">Notify Me via {{oidc_name}}</button>
    </form>
  </div>
  <span class="spacer"></span>
  <div class="linkRow">
    <a href="/">Got another link?</a>
  </div>
</main>
